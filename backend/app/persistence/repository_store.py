"""The PostgreSQL store for Git repository records, with credential-safe failure stamping."""

import uuid
from datetime import datetime

from sqlmodel import Session, func, select

from app.enums.repository import RepositoryStatus
from app.errors.git_errors import GitError
from app.models.repository import Repository


class RepositoryStore:
    """Persist Git repository records through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, repository_id: uuid.UUID) -> Repository | None:
        """Load a repository by id, or ``None`` if absent."""
        return self.session.get(Repository, repository_id)

    def get_by_user_id(self, user_id: uuid.UUID) -> list[Repository]:
        """Return all of a user's repositories."""
        statement = select(Repository).where(Repository.user_id == user_id)
        return list(self.session.exec(statement).all())

    def get_page(self, *, skip: int, limit: int, user_id: uuid.UUID | None = None) -> list[Repository]:
        """Return a page of repositories, optionally scoped to one user."""
        statement = select(Repository)
        if user_id is not None:
            statement = statement.where(Repository.user_id == user_id)
        statement = statement.offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def count(self, *, user_id: uuid.UUID | None = None) -> int:
        """Count repositories, optionally scoped to one user."""
        statement = select(func.count()).select_from(Repository)
        if user_id is not None:
            statement = statement.where(Repository.user_id == user_id)
        return self.session.exec(statement).one()

    def get_by_url_and_user_id(self, repository_url: str, user_id: uuid.UUID) -> Repository | None:
        """Find a user's repository by URL, used to detect duplicates."""
        statement = select(Repository).where(Repository.user_id == user_id, Repository.repository_url == repository_url)
        return self.session.exec(statement).first()

    def save(self, repository: Repository) -> Repository:
        """Persist a repository and return the refreshed row."""
        self.session.add(repository)
        self.session.commit()
        self.session.refresh(repository)
        return repository

    def update_token(self, repository: Repository, *, encrypted_token: str, token_expiration_date: datetime | None) -> Repository:
        """Replace the stored access token and its expiry."""
        repository.encrypted_token = encrypted_token
        repository.token_expiration_date = token_expiration_date
        return self.save(repository)

    def begin_cloning(self, repository: Repository) -> Repository:
        """Enter the cloning state, discarding any stale failure reason."""
        repository.status = RepositoryStatus.cloning
        repository.failed_reason = None
        return self.save(repository)

    def begin_indexing(self, repository: Repository) -> Repository:
        """Enter the indexing state once the checkout is recorded."""
        repository.status = RepositoryStatus.indexing
        return self.save(repository)

    def record_checkout(self, repository: Repository, *, local_path: str, default_branch: str) -> Repository:
        """Persist where the Git checkout landed and the branch it tracks."""
        repository.local_path = local_path
        repository.default_branch = default_branch
        return self.save(repository)

    def mark_ready(self, repository: Repository, *, indexed_commit_sha: str) -> Repository:
        """Publish successfully indexed Repository Evidence."""
        repository.indexed_commit_sha = indexed_commit_sha
        repository.status = RepositoryStatus.ready
        repository.failed_reason = None
        return self.save(repository)

    def fail(self, repository: Repository, exc: Exception, *, credential: str | None, fallback: str = "Repository processing failed") -> str:
        """Stamp a credential-sanitized failure reason alongside the failed status."""
        reason = _sanitized_failure(exc, credential, fallback=fallback)
        repository.status = RepositoryStatus.failed
        repository.failed_reason = reason
        self.save(repository)
        return reason

    def delete(self, repository: Repository) -> None:
        """Delete a repository and its cascaded records."""
        self.session.delete(repository)
        self.session.commit()

    def rollback(self) -> None:
        """Roll back the current session transaction."""
        self.session.rollback()


def _sanitized_failure(exc: Exception, credential: str | None, *, fallback: str = "Repository processing failed") -> str:
    """Return a bounded failure message that cannot expose credentials."""
    if isinstance(exc, (GitError, ValueError)):
        reason = str(exc)
    else:
        reason = fallback
    if credential:
        reason = reason.replace(credential, "[REDACTED]")
    return reason[:1000]
