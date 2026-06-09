"""Coordinate repository registration, credential storage, cloning, and indexing.

The service layer translates raw API input into validated repository identities
and HTTP errors. Git process details remain in ``app.git``, while persistence
and repository status transitions are coordinated here.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.db import engine
from app.core.security import decrypt_repository_token, encrypt_repository_token
from app.core.weaviate_init import WeaviateResources
from app.errors.git_errors import GitError
from app.git.git_commands import GitCommands
from app.git.repository_url import ParsedRepositoryUrl, parse_repository_url
from app.models.git_repositories import GitRepository, GitRepositoryProvider, GitRepositoryStatus
from app.rag.ingestor import DocumentIngestor
from app.repositories.git_repository_repository import GitRepositoryRepository

logger = logging.getLogger(__name__)


class RepositoryService:
    """Register repositories and schedule their asynchronous processing."""

    def __init__(self, db_repo: GitRepositoryRepository):
        """Create the service with its repository persistence adapter."""
        self.db_repo = db_repo

    def repository_create(
        self,
        *,
        repo_url: str,
        token: str,
        token_expiration_days: int | None,
        user_id: uuid.UUID,
        background_tasks: BackgroundTasks,
        weaviate_resources: WeaviateResources,
    ) -> GitRepository:
        """Validate and persist a pending repository for one user.

        The access token is encrypted before persistence. Equivalent SSH and
        HTTPS URLs are treated as duplicates for the same user.

        Raises:
            HTTPException: With status 422 for invalid URLs or 409 for duplicate
                repositories.

        """
        try:
            parsed_url = parse_repository_url(repo_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        if self._find_duplicate(parsed_url.canonical_url, user_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists")

        expiration_date = None
        if token_expiration_days is not None:
            expiration_date = datetime.now(UTC) + timedelta(days=token_expiration_days)

        repository = GitRepository(
            user_id=user_id,
            name=parsed_url.name,
            repository_url=parsed_url.canonical_url,
            owner=parsed_url.owner,
            provider=_provider_for(parsed_url),
            encrypted_token=encrypt_repository_token(token),
            token_expiration_date=expiration_date,
            status=GitRepositoryStatus.pending,
        )

        try:
            self.db_repo.save(repository)
        except IntegrityError as exc:
            self.db_repo.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists") from exc

        background_tasks.add_task(process_repository, repository.id, weaviate_resources)
        return repository

    def _find_duplicate(self, canonical_url: str, user_id: uuid.UUID) -> GitRepository | None:
        """Find a canonical or legacy-equivalent repository for one user."""
        repository = self.db_repo.get_by_url_and_user_id(canonical_url, user_id)
        if repository:
            return repository

        # Catch records created before canonical HTTPS storage was enforced.
        for candidate in self.db_repo.get_by_user_id(user_id):
            try:
                if parse_repository_url(candidate.repository_url).canonical_url == canonical_url:
                    return candidate
            except ValueError:
                continue
        return None


def process_repository(repository_id: uuid.UUID, weaviate_resources: WeaviateResources) -> None:
    """Clone and index a pending repository while persisting status transitions.

    This function is suitable for FastAPI background-task execution. Failures
    are converted into a sanitized ``failed_reason`` so credentials and
    unexpected exception details are not persisted.
    """
    token: str | None = None
    with Session(engine) as session:
        repositories = GitRepositoryRepository(session)
        repository = repositories.get_by_id(repository_id)
        if not repository or repository.status == GitRepositoryStatus.ready:
            return

        try:
            token = _active_token(repository)
            repositories.update_status(repository, GitRepositoryStatus.cloning)

            parsed_url = parse_repository_url(repository.repository_url)
            git = GitCommands(parsed_url, repository.user_id)
            git.clone(token)
            repository.local_path = str(git.repo_path)
            repository.default_branch = git.get_default_branch()
            repositories.update_status(repository, GitRepositoryStatus.cloned)

            repositories.update_status(repository, GitRepositoryStatus.indexing)
            DocumentIngestor(weaviate_resources).ingest(git.repo_path, repository.id, repository.default_branch, repository.user_id)
            repositories.update_status(repository, GitRepositoryStatus.ready)
        except Exception as exc:
            session.rollback()
            repository = repositories.get_by_id(repository_id)
            if repository:
                repositories.update_status(repository, GitRepositoryStatus.failed, failed_reason=_sanitized_failure(exc, token))
            logger.error("Repository processing failed for repository_id=%s: %s", repository_id, _sanitized_failure(exc, token))


def _active_token(repository: GitRepository) -> str:
    """Decrypt repository credentials after checking presence and expiration."""
    if not repository.encrypted_token:
        raise ValueError("Repository credentials are missing")

    expiration = repository.token_expiration_date
    if expiration is not None:
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=UTC)
        if expiration <= datetime.now(UTC):
            raise ValueError("Repository token has expired")

    return decrypt_repository_token(repository.encrypted_token)


def _provider_for(parsed_url: ParsedRepositoryUrl) -> GitRepositoryProvider:
    """Map an allowlisted repository host to its persisted provider enum."""
    providers = {"github.com": GitRepositoryProvider.github, "gitlab.com": GitRepositoryProvider.gitlab, "bitbucket.org": GitRepositoryProvider.bitbucket}
    return providers[parsed_url.host]


def _sanitized_failure(exc: Exception, token: str | None) -> str:
    """Return a bounded failure message that cannot expose the repository token."""
    if isinstance(exc, (GitError, ValueError)):
        reason = str(exc)
    else:
        reason = "Repository processing failed"
    if token:
        reason = reason.replace(token, "[REDACTED]")
    return reason[:1000]
