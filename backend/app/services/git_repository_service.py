"""Coordinate repository persistence, credentials, processing, and cleanup."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.db import engine
from app.core.security import encrypt_repository_token
from app.core.vector_db import WeaviateResources
from app.errors.git_errors import GitError
from app.git.git_commands import GitCommands
from app.git.repository_url import ParsedRepositoryUrl, parse_repository_url
from app.models.git_repositories import (
    GitRepositoriesPublic,
    GitRepository,
    GitRepositoryCreate,
    GitRepositoryProvider,
    GitRepositoryStatus,
    GitRepositoryUpdate,
)
from app.models.users import User
from app.rag.ingestor import DocumentIngestor
from app.repositories.git_repository_repository import GitRepositoryRepository

logger = logging.getLogger(__name__)

GitCommandsFactory = Callable[[ParsedRepositoryUrl, uuid.UUID], GitCommands]
ACTIVE_PROCESSING_STATUSES = {GitRepositoryStatus.pending, GitRepositoryStatus.cloning, GitRepositoryStatus.cloned, GitRepositoryStatus.indexing}


class RepositoryService:
    """Own repository authorization and business workflows."""

    def __init__(self, db_repo: GitRepositoryRepository, ingestor: DocumentIngestor, git_commands_factory: GitCommandsFactory = GitCommands) -> None:
        self.db_repo = db_repo
        self.ingestor = ingestor
        self.git_commands_factory = git_commands_factory

    def repository_list(self, *, user: User, skip: int, limit: int) -> GitRepositoriesPublic:
        """Return the repositories visible to a user."""
        owner_id = None if user.is_superuser else user.id
        repositories = self.db_repo.get_page(skip=skip, limit=limit, user_id=owner_id)
        return GitRepositoriesPublic(data=repositories, count=self.db_repo.count(user_id=owner_id))

    def repository_get(self, *, repository_id: uuid.UUID, user: User) -> GitRepository:
        """Return one accessible repository."""
        return self._get_accessible(repository_id, user)

    def repository_create(
        self, *, repository: GitRepositoryCreate, user: User, background_tasks: BackgroundTasks, weaviate_resources: WeaviateResources
    ) -> GitRepository:
        """Validate, persist, and enqueue a repository for processing."""
        try:
            parsed_url = parse_repository_url(repository.repository_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        if self._find_duplicate(parsed_url.canonical_url, user.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists")

        repository_record = GitRepository(
            user_id=user.id,
            name=parsed_url.name,
            repository_url=parsed_url.canonical_url,
            owner=parsed_url.owner,
            provider=_provider_for(parsed_url),
            encrypted_token=encrypt_repository_token(repository.token),
            token_expiration_date=_expiration_date(repository.token_expiration_days),
            status=GitRepositoryStatus.pending,
        )

        try:
            self.db_repo.save(repository_record)
        except IntegrityError as exc:
            self.db_repo.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists") from exc

        background_tasks.add_task(process_repository, repository_record.id, repository.token, weaviate_resources)
        return repository_record

    def repository_update(self, *, repository_id: uuid.UUID, repository: GitRepositoryUpdate, user: User) -> None:
        """Replace only a repository's encrypted token and expiration date."""
        repository_record = self._get_accessible(repository_id, user)
        self.db_repo.update_token(
            repository_record,
            encrypted_token=encrypt_repository_token(repository.token),
            token_expiration_date=_expiration_date(repository.token_expiration_days),
        )

    def repository_delete(self, *, repository_id: uuid.UUID, user: User) -> None:
        """Delete local, vector, and relational repository state."""
        repository = self._get_accessible(repository_id, user)
        if repository.status in ACTIVE_PROCESSING_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository cannot be deleted while processing")

        parsed_url = parse_repository_url(repository.repository_url)
        git = self.git_commands_factory(parsed_url, repository.user_id)
        git.delete_checkout()
        self.ingestor.delete_by_repository(repository.id, user_id=repository.user_id)
        self.db_repo.delete(repository)

    def process_repository(self, repository_id: uuid.UUID, token: str) -> None:
        """Clone and index a pending repository, persisting each transition."""
        repository = self.db_repo.get_by_id(repository_id)
        if not repository or repository.status == GitRepositoryStatus.ready:
            return

        try:
            self.db_repo.update_status(repository, GitRepositoryStatus.cloning)

            parsed_url = parse_repository_url(repository.repository_url)
            git = self.git_commands_factory(parsed_url, repository.user_id)
            git.clone(token)
            repository.local_path = str(git.repo_path)
            repository.default_branch = git.get_default_branch()
            self.db_repo.update_status(repository, GitRepositoryStatus.cloned)

            self.db_repo.update_status(repository, GitRepositoryStatus.indexing)
            self.ingestor.ingest(git.repo_path, repository.id, repository.default_branch, repository.user_id)
            self.db_repo.update_status(repository, GitRepositoryStatus.ready)
        except Exception as exc:
            self.db_repo.rollback()
            repository = self.db_repo.get_by_id(repository_id)
            if repository:
                self.db_repo.update_status(repository, GitRepositoryStatus.failed, failed_reason=_sanitized_failure(exc, token))
            logger.error("Repository processing failed for repository_id=%s: %s", repository_id, _sanitized_failure(exc, token))

    def _get_accessible(self, repository_id: uuid.UUID, user: User) -> GitRepository:
        repository = self.db_repo.get_by_id(repository_id)
        if not repository:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if not user.is_superuser and repository.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return repository

    def _find_duplicate(self, canonical_url: str, user_id: uuid.UUID) -> GitRepository | None:
        repository = self.db_repo.get_by_url_and_user_id(canonical_url, user_id)
        if repository:
            return repository

        for candidate in self.db_repo.get_by_user_id(user_id):
            try:
                if parse_repository_url(candidate.repository_url).canonical_url == canonical_url:
                    return candidate
            except ValueError:
                continue
        return None


def process_repository(repository_id: uuid.UUID, token: str, weaviate_resources: WeaviateResources) -> None:
    """Compose fresh request-independent dependencies for background work."""
    with Session(engine) as session:
        RepositoryService(GitRepositoryRepository(session), DocumentIngestor(weaviate_resources)).process_repository(repository_id, token)


def _expiration_date(token_expiration_days: int | None) -> datetime | None:
    if token_expiration_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=token_expiration_days)


def _provider_for(parsed_url: ParsedRepositoryUrl) -> GitRepositoryProvider:
    providers = {"github.com": GitRepositoryProvider.github, "gitlab.com": GitRepositoryProvider.gitlab, "bitbucket.org": GitRepositoryProvider.bitbucket}
    return providers[parsed_url.host]


def _sanitized_failure(exc: Exception, token: str | None) -> str:
    """Return a bounded failure message that cannot expose credentials."""
    if isinstance(exc, (GitError, ValueError)):
        reason = str(exc)
    else:
        reason = "Repository processing failed"
    if token:
        reason = reason.replace(token, "[REDACTED]")
    return reason[:1000]
