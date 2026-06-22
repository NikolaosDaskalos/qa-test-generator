"""Coordinate Git repository persistence, credentials, processing, and cleanup."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core import encrypt_repository_token
from app.core.errors.git_errors import GitError
from app.core.errors.repository_errors import (
    DuplicateRepository,
    InvalidRepositoryCredential,
    InvalidRepositoryUrl,
    RepositoryAccessForbidden,
    RepositoryDeletionFailed,
    RepositoryNotFound,
    RepositoryProcessing,
)
from app.db import engine
from app.db.models import Repository, User
from app.db.persistence import RepositoryDocumentStore, RepositoryStore
from app.enums import RepositoryProvider, RepositoryStatus
from app.integrations.git import GitCommands, ParsedRepositoryUrl, parse_repository_url
from app.integrations.weaviate import WeaviateResources
from app.rag import DocumentIngestor
from app.schemas import RepositoriesPublic, RepositoryCreate, RepositoryUpdate
from app.services.background import BackgroundScheduler

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
        user_id = None if user.is_superuser else user.id
        repositories = self.repository_store.get_page(skip=skip, limit=limit, user_id=user_id)
        count = self.repository_store.count(user_id=user_id)
        logger.info("Listed repositories user_id=%s returned_count=%s total_count=%s", user.id, len(repositories), count)
        return RepositoriesPublic(data=repositories, count=count)  # type: ignore[arg-type]

    def get_repository(self, *, repository_id: uuid.UUID, user: User) -> Repository:
        """Return one accessible Git repository."""
        logger.info("Getting repository repository_id=%s user_id=%s", repository_id, user.id)
        return self._get_accessible(repository_id, user)

    def create_repository(
        self, *, repository_in: RepositoryCreate, user: User, background_tasks: BackgroundScheduler, weaviate_resources: WeaviateResources
    ) -> Repository:
        """Validate, persist, and enqueue a Git repository for processing."""
        try:
            parsed_url = parse_repository_url(repository_in.repository_url)
        except ValueError as exc:
            logger.warning("Repository creation rejected for user_id=%s: %s", user.id, exc)
            raise InvalidRepositoryUrl(str(exc)) from exc

        if self._find_duplicate(parsed_url.canonical_url, user.id):
            logger.warning(
                "Duplicate repository creation rejected user_id=%s host=%s owner=%s repository=%s", user.id, parsed_url.host, parsed_url.owner, parsed_url.name
            )
            raise DuplicateRepository

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
            raise DuplicateRepository from exc

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
            raise InvalidRepositoryCredential from exc

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
            raise RepositoryProcessing

        user_id = repository.user_id
        encrypted_token = repository.encrypted_token
        logger.info("Repository deletion started repository_id=%s user_id=%s", repository_id, user_id)
        try:
            parsed_url = parse_repository_url(repository.repository_url)
            git = self.git_commands_factory(parsed_url, user_id)
            git.delete_checkout()
        except Exception as exc:
            reason = self.repository_store.fail(repository, exc, credential=encrypted_token, fallback="Repository checkout deletion failed")
            logger.error("Repository checkout deletion failed repository_id=%s: %s", repository_id, reason)
            raise RepositoryDeletionFailed from exc
        try:
            self.ingestor.delete_repository(repository_id, user_id=user_id)
        except Exception as exc:
            reason = self.repository_store.fail(repository, exc, credential=encrypted_token, fallback="Repository vector deletion failed")
            logger.error("Repository vector deletion failed repository_id=%s: %s", repository_id, reason)
            raise RepositoryDeletionFailed from exc
        try:
            self.repository_store.delete(repository)
        except Exception as exc:
            self.repository_store.rollback()
            repository = self.repository_store.get_by_id(repository_id)
            if repository:
                reason = self.repository_store.fail(repository, exc, credential=encrypted_token, fallback="Repository database deletion failed")
            else:
                reason = "Repository database deletion failed"
            logger.error("Repository database deletion failed repository_id=%s: %s", repository_id, reason)
            raise RepositoryDeletionFailed from exc
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
            self.repository_store.begin_cloning(repository)
            logger.info("Repository status changed repository_id=%s status=%s", repository.id, RepositoryStatus.cloning.value)

            parsed_url = parse_repository_url(repository.repository_url)
            git = self.git_commands_factory(parsed_url, repository.user_id)
            git.clone(token)
            default_branch = git.get_default_branch()
            git.checkout(default_branch)
            checkout_commit_sha = git.get_current_commit_sha()
            self.repository_store.record_checkout(repository, local_path=str(git.repo_path), default_branch=default_branch)

            self.repository_store.begin_indexing(repository)
            logger.info(
                "Repository status changed repository_id=%s status=%s default_branch=%s", repository.id, RepositoryStatus.indexing.value, default_branch
            )
            chunk_count = self.ingestor.ingest(git.repo_path, repository.id, default_branch, checkout_commit_sha, repository.user_id)
            if chunk_count == 0:
                raise ValueError("Repository contains no usable Python files")
            self.repository_store.mark_ready(repository, indexed_commit_sha=checkout_commit_sha)
            logger.info("Repository processing completed repository_id=%s status=%s chunk_count=%s", repository.id, RepositoryStatus.ready.value, chunk_count)
        except Exception as exc:
            self.repository_store.rollback()
            repository = self.repository_store.get_by_id(repository_id)
            if repository:
                reason = self.repository_store.fail(repository, exc, credential=token)
                logger.error("Git repository processing failed for repository_id=%s: %s", repository_id, reason)
            else:
                logger.error("Git repository processing failed for repository_id=%s; record no longer exists", repository_id)

    def _get_accessible(self, repository_id: uuid.UUID, user: User) -> Repository:
        """Return a repository the user can access, raising 404 if missing or 403 if not theirs."""
        repository = self.repository_store.get_by_id(repository_id)
        if not repository:
            logger.warning("Repository access failed because it was not found repository_id=%s user_id=%s", repository_id, user.id)
            raise RepositoryNotFound
        if not user.is_superuser and repository.user_id != user.id:
            logger.warning("Repository access denied repository_id=%s user_id=%s", repository_id, user.id)
            raise RepositoryAccessForbidden
        return repository

    def _find_duplicate(self, canonical_url: str, user_id: uuid.UUID) -> Repository | None:
        """Find the user's existing repository matching ``canonical_url``, comparing canonical forms."""
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
        repository_document_store = RepositoryDocumentStore(session)
        RepositoryService(RepositoryStore(session), DocumentIngestor(weaviate_resources, repository_document_store)).process_repository(repository_id, token)
    logger.info("Repository background task closed repository_id=%s", repository_id)


def _expiration_date(token_expiration_days: int | None) -> datetime | None:
    """Convert a token lifetime in days to an absolute UTC expiry, or ``None`` for no expiry."""
    if token_expiration_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=token_expiration_days)


def _provider_for(parsed_url: ParsedRepositoryUrl) -> RepositoryProvider:
    """Map a parsed URL to its provider, raising for unsupported hosts (only GitHub today)."""
    if parsed_url.host != "github.com":
        raise ValueError("Repository provider is not supported")
    return RepositoryProvider.github
