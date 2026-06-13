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
from app.enums.repository import RepositoryProvider, RepositoryStatus
from app.errors.git_errors import GitError
from app.git.git_commands import GitCommands
from app.git.repository_url import ParsedRepositoryUrl, parse_repository_url
from app.models.repository import Repository
from app.models.user import User
from app.persistence.repository_store import RepositoryStore
from app.persistence.source_document_store import SourceDocumentStore
from app.rag.ingestor import DocumentIngestor
from app.schemas.repository import RepositoriesPublic, RepositoryCreate, RepositoryUpdate

logger = logging.getLogger(__name__)

GitCommandsFactory = Callable[[ParsedRepositoryUrl, uuid.UUID], GitCommands]
ACTIVE_PROCESSING_STATUSES = {RepositoryStatus.pending, RepositoryStatus.cloning, RepositoryStatus.indexing}


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
        count = self.repository_store.count(user_id=owner_id)
        logger.info("Listed repositories user_id=%s returned_count=%s total_count=%s", user.id, len(repositories), count)
        return RepositoriesPublic(data=repositories, count=count)  # type: ignore[arg-type]

    def get_repository(self, *, repository_id: uuid.UUID, user: User) -> Repository:
        """Return one accessible Git repository."""
        logger.info("Getting repository repository_id=%s user_id=%s", repository_id, user.id)
        return self._get_accessible(repository_id, user)

    def create_repository(
        self, *, repository_in: RepositoryCreate, user: User, background_tasks: BackgroundTasks, weaviate_resources: WeaviateResources
    ) -> Repository:
        """Validate, persist, and enqueue a Git repository for processing."""
        try:
            parsed_url = parse_repository_url(repository_in.repository_url)
        except ValueError as exc:
            logger.warning("Repository creation rejected for user_id=%s: %s", user.id, exc)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        if self._find_duplicate(parsed_url.canonical_url, user.id):
            logger.warning(
                "Duplicate repository creation rejected user_id=%s host=%s owner=%s repository=%s", user.id, parsed_url.host, parsed_url.owner, parsed_url.name
            )
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
            logger.warning("Repository creation hit a uniqueness conflict user_id=%s repository_id=%s", user.id, repository.id)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already exists") from exc

        background_tasks.add_task(process_repository, repository.id, repository_in.token, weaviate_resources)
        logger.info("Repository created and processing scheduled repository_id=%s user_id=%s", repository.id, user.id)
        return repository

    def update_repository(self, *, repository_id: uuid.UUID, repository_in: RepositoryUpdate, user: User) -> None:
        """Validate and replace a Git repository's encrypted credentials."""
        repository = self._get_accessible(repository_id, user)
        parsed_url = parse_repository_url(repository.repository_url)
        git = self.git_commands_factory(parsed_url, repository.user_id)
        try:
            git.validate_remote_access(repository_in.token)
        except GitError as exc:
            logger.warning("Repository credential validation failed repository_id=%s user_id=%s", repository.id, user.id)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is invalid for repository") from exc

        self.repository_store.update_token(
            repository,
            encrypted_token=encrypt_repository_token(repository_in.token),
            token_expiration_date=_expiration_date(repository_in.token_expiration_days),
        )
        logger.info("Repository credentials updated repository_id=%s user_id=%s", repository.id, user.id)

    def delete_repository(self, *, repository_id: uuid.UUID, user: User) -> None:
        """Delete local, vector, and relational Git repository state."""
        repository = self._get_accessible(repository_id, user)
        if repository.status in ACTIVE_PROCESSING_STATUSES:
            logger.warning("Repository deletion blocked while processing repository_id=%s status=%s", repository.id, repository.status.value)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository cannot be deleted while processing")

        user_id = repository.user_id
        encrypted_token = repository.encrypted_token
        logger.info("Repository deletion started repository_id=%s user_id=%s", repository_id, user_id)
        try:
            parsed_url = parse_repository_url(repository.repository_url)
            git = self.git_commands_factory(parsed_url, user_id)
            git.delete_checkout()
        except Exception as exc:
            reason = _sanitized_failure(exc, encrypted_token, fallback="Repository checkout deletion failed")
            self.repository_store.update_status(repository, RepositoryStatus.failed, failed_reason=reason)
            logger.error("Repository checkout deletion failed repository_id=%s: %s", repository_id, reason)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Repository deletion failed") from exc
        try:
            self.ingestor.delete_repository(repository_id, user_id=user_id)
        except Exception as exc:
            reason = _sanitized_failure(exc, encrypted_token, fallback="Repository vector deletion failed")
            self.repository_store.update_status(repository, RepositoryStatus.failed, failed_reason=reason)
            logger.error("Repository vector deletion failed repository_id=%s: %s", repository_id, reason)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Repository deletion failed") from exc
        try:
            self.repository_store.delete(repository)
        except Exception as exc:
            reason = _sanitized_failure(exc, encrypted_token, fallback="Repository database deletion failed")
            self.repository_store.rollback()
            repository = self.repository_store.get_by_id(repository_id)
            if repository:
                self.repository_store.update_status(repository, RepositoryStatus.failed, failed_reason=reason)
            logger.error("Repository database deletion failed repository_id=%s: %s", repository_id, reason)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Repository deletion failed") from exc
        logger.info("Repository deletion completed repository_id=%s user_id=%s", repository_id, user_id)

    def process_repository(self, repository_id: uuid.UUID, token: str) -> None:
        """Clone and index a pending Git repository, persisting each transition."""
        repository = self.repository_store.get_by_id(repository_id)
        if not repository:
            logger.warning("Repository processing skipped because the record does not exist repository_id=%s", repository_id)
            return
        if repository.status == RepositoryStatus.ready:
            logger.info("Repository processing skipped because it is already ready repository_id=%s", repository_id)
            return

        try:
            logger.info("Repository processing started repository_id=%s user_id=%s", repository.id, repository.user_id)
            self.repository_store.update_status(repository, RepositoryStatus.cloning)
            logger.info("Repository status changed repository_id=%s status=%s", repository.id, RepositoryStatus.cloning.value)

            parsed_url = parse_repository_url(repository.repository_url)
            git = self.git_commands_factory(parsed_url, repository.user_id)
            git.clone(token)
            repository.local_path = str(git.repo_path)
            repository.default_branch = git.get_default_branch()
            git.checkout(repository.default_branch)
            checkout_commit_sha = git.get_current_commit_sha()

            self.repository_store.update_status(repository, RepositoryStatus.indexing)
            logger.info(
                "Repository status changed repository_id=%s status=%s default_branch=%s",
                repository.id,
                RepositoryStatus.indexing.value,
                repository.default_branch,
            )
            chunk_count = self.ingestor.ingest(git.repo_path, repository.id, repository.default_branch, checkout_commit_sha, repository.user_id)
            if chunk_count == 0:
                raise ValueError("Repository contains no usable Python files")
            self.repository_store.mark_ready(repository, indexed_commit_sha=checkout_commit_sha)
            logger.info("Repository processing completed repository_id=%s status=%s chunk_count=%s", repository.id, RepositoryStatus.ready.value, chunk_count)
        except Exception as exc:
            self.repository_store.rollback()
            repository = self.repository_store.get_by_id(repository_id)
            if repository:
                self.repository_store.update_status(repository, RepositoryStatus.failed, failed_reason=_sanitized_failure(exc, token))
            logger.error("Git repository processing failed for repository_id=%s: %s", repository_id, _sanitized_failure(exc, token))

    def _get_accessible(self, repository_id: uuid.UUID, user: User) -> Repository:
        repository = self.repository_store.get_by_id(repository_id)
        if not repository:
            logger.warning("Repository access failed because it was not found repository_id=%s user_id=%s", repository_id, user.id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if not user.is_superuser and repository.user_id != user.id:
            logger.warning("Repository access denied repository_id=%s user_id=%s", repository_id, user.id)
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
    logger.info("Repository background task opened repository_id=%s", repository_id)
    with Session(engine) as session:
        source_document_store = SourceDocumentStore(session)
        RepositoryService(RepositoryStore(session), DocumentIngestor(weaviate_resources, source_document_store)).process_repository(repository_id, token)
    logger.info("Repository background task closed repository_id=%s", repository_id)


def _expiration_date(token_expiration_days: int | None) -> datetime | None:
    if token_expiration_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=token_expiration_days)


def _provider_for(parsed_url: ParsedRepositoryUrl) -> RepositoryProvider:
    if parsed_url.host != "github.com":
        raise ValueError("Repository provider is not supported")
    return RepositoryProvider.github


def _sanitized_failure(exc: Exception, token: str | None, *, fallback: str = "Repository processing failed") -> str:
    """Return a bounded failure message that cannot expose credentials."""
    if isinstance(exc, (GitError, ValueError)):
        reason = str(exc)
    else:
        reason = fallback
    if token:
        reason = reason.replace(token, "[REDACTED]")
    return reason[:1000]
