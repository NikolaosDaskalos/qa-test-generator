"""Coordinate Git repository persistence, credentials, processing, and cleanup."""

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
from app.models.repository import RepositoriesPublic, Repository, RepositoryCreate, RepositoryProvider, RepositoryStatus, RepositoryUpdate
from app.models.users import User
from app.persistence.repository_store import RepositoryStore
from app.rag.ingestor import DocumentIngestor

logger = logging.getLogger(__name__)

GitCommandsFactory = Callable[[ParsedRepositoryUrl, uuid.UUID], GitCommands]
ACTIVE_PROCESSING_STATUSES = {RepositoryStatus.pending, RepositoryStatus.cloning, RepositoryStatus.cloned, RepositoryStatus.indexing}


class RepositoryService:
    """Own Git repository authorization and business workflows."""

    def __init__(self, repository_store: RepositoryStore, ingestor: DocumentIngestor, git_commands_factory: GitCommandsFactory = GitCommands) -> None:
        self.repository_store = repository_store
        self.ingestor = ingestor
        self.git_commands_factory = git_commands_factory

    def list_repositories(self, *, user: User, skip: int, limit: int) -> RepositoriesPublic:
        """Return the Git repositories visible to a user."""
        owner_id = None if user.is_superuser else user.id
        repositories = self.repository_store.get_page(skip=skip, limit=limit, user_id=owner_id)
        return RepositoriesPublic(data=repositories, count=self.repository_store.count(user_id=owner_id))

    def get_repository(self, *, repository_id: uuid.UUID, user: User) -> Repository:
        """Return one accessible Git repository."""
        return self._get_accessible(repository_id, user)

    def create_repository(
        self, *, repository_in: RepositoryCreate, user: User, background_tasks: BackgroundTasks, weaviate_resources: WeaviateResources
    ) -> Repository:
        """Validate, persist, and enqueue a Git repository for processing."""
        try:
            parsed_url = parse_repository_url(repository_in.repository_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        if self._find_duplicate(parsed_url.canonical_url, user.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists")

        repository = Repository(
            user_id=user.id,
            name=parsed_url.name,
            repository_url=parsed_url.canonical_url,
            owner=parsed_url.owner,
            provider=_provider_for(parsed_url),
            encrypted_token=encrypt_repository_token(repository_in.token),
            token_expiration_date=_expiration_date(repository_in.token_expiration_days),
            status=RepositoryStatus.pending,
        )

        try:
            self.repository_store.save(repository)
        except IntegrityError as exc:
            self.repository_store.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists") from exc

        background_tasks.add_task(process_repository, repository.id, repository_in.token, weaviate_resources)
        return repository

    def update_repository(self, *, repository_id: uuid.UUID, repository_in: RepositoryUpdate, user: User) -> None:
        """Replace only a Git repository's encrypted token and expiration date."""
        repository = self._get_accessible(repository_id, user)
        self.repository_store.update_token(
            repository,
            encrypted_token=encrypt_repository_token(repository_in.token),
            token_expiration_date=_expiration_date(repository_in.token_expiration_days),
        )

    def delete_repository(self, *, repository_id: uuid.UUID, user: User) -> None:
        """Delete local, vector, and relational Git repository state."""
        repository = self._get_accessible(repository_id, user)
        if repository.status in ACTIVE_PROCESSING_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository cannot be deleted while processing")

        parsed_url = parse_repository_url(repository.repository_url)
        git = self.git_commands_factory(parsed_url, repository.user_id)
        git.delete_checkout()
        self.ingestor.delete_by_repository(repository.id, user_id=repository.user_id)
        self.repository_store.delete(repository)

    def process_repository(self, repository_id: uuid.UUID, token: str) -> None:
        """Clone and index a pending Git repository, persisting each transition."""
        repository = self.repository_store.get_by_id(repository_id)
        if not repository or repository.status == RepositoryStatus.ready:
            return

        try:
            self.repository_store.update_status(repository, RepositoryStatus.cloning)

            parsed_url = parse_repository_url(repository.repository_url)
            git = self.git_commands_factory(parsed_url, repository.user_id)
            git.clone(token)
            repository.local_path = str(git.repo_path)
            repository.default_branch = git.get_default_branch()
            self.repository_store.update_status(repository, RepositoryStatus.cloned)

            self.repository_store.update_status(repository, RepositoryStatus.indexing)
            self.ingestor.ingest(git.repo_path, repository.id, repository.default_branch, repository.user_id)
            self.repository_store.update_status(repository, RepositoryStatus.ready)
        except Exception as exc:
            self.repository_store.rollback()
            repository = self.repository_store.get_by_id(repository_id)
            if repository:
                self.repository_store.update_status(repository, RepositoryStatus.failed, failed_reason=_sanitized_failure(exc, token))
            logger.error("Git repository processing failed for repository_id=%s: %s", repository_id, _sanitized_failure(exc, token))

    def _get_accessible(self, repository_id: uuid.UUID, user: User) -> Repository:
        repository = self.repository_store.get_by_id(repository_id)
        if not repository:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if not user.is_superuser and repository.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return repository

    def _find_duplicate(self, canonical_url: str, user_id: uuid.UUID) -> Repository | None:
        repository = self.repository_store.get_by_url_and_user_id(canonical_url, user_id)
        if repository:
            return repository

        for candidate in self.repository_store.get_by_user_id(user_id):
            try:
                if parse_repository_url(candidate.repository_url).canonical_url == canonical_url:
                    return candidate
            except ValueError:
                continue
        return None


def process_repository(repository_id: uuid.UUID, token: str, weaviate_resources: WeaviateResources) -> None:
    """Compose fresh request-independent dependencies for background work."""
    with Session(engine) as session:
        RepositoryService(RepositoryStore(session), DocumentIngestor(weaviate_resources)).process_repository(repository_id, token)


def _expiration_date(token_expiration_days: int | None) -> datetime | None:
    if token_expiration_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=token_expiration_days)


def _provider_for(parsed_url: ParsedRepositoryUrl) -> RepositoryProvider:
    providers = {"github.com": RepositoryProvider.github, "gitlab.com": RepositoryProvider.gitlab, "bitbucket.org": RepositoryProvider.bitbucket}
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
