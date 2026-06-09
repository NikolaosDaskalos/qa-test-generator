"""Test repository registration and background processing workflows."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core.security import decrypt_repository_token, encrypt_repository_token
from app.core.vector_db import WeaviateResources
from app.errors.git_errors import GitError
from app.git.repository_url import ParsedRepositoryUrl
from app.models.git_repositories import GitRepository, GitRepositoryStatus
from app.services import git_repository_service
from app.services.git_repository_service import RepositoryService


class FakeSession:
    """Provide the rollback behavior used by the service."""

    def rollback(self) -> None:
        """Accept rollback calls without persistence side effects."""
        pass


class FakeRepositoryStore:
    """Store one repository and record status transitions in memory."""

    def __init__(self, repository: GitRepository | None = None):
        """Initialize the store with an optional repository."""
        self.session = FakeSession()
        self.repository = repository
        self.saved: list[GitRepository] = []
        self.statuses: list[GitRepositoryStatus] = []

    def get_by_url_and_user_id(self, repository_url, user_id):
        """Return the repository when its URL and owner match."""
        if self.repository and self.repository.repository_url == repository_url and self.repository.user_id == user_id:
            return self.repository
        return None

    def get_by_user_id(self, user_id):
        """Return repositories owned by the requested user."""
        if self.repository and self.repository.user_id == user_id:
            return [self.repository]
        return []

    def get_by_id(self, repository_id):
        """Return the repository matching the requested ID."""
        if self.repository and self.repository.id == repository_id:
            return self.repository
        return None

    def save(self, repository):
        """Persist and record a repository."""
        self.repository = repository
        self.saved.append(repository)
        return repository

    def update_status(self, repository, status, *, failed_reason=None):
        """Apply and record a repository status transition."""
        repository.status = status
        repository.failed_reason = failed_reason
        self.statuses.append(status)
        return repository


def make_repository(**updates: Any) -> GitRepository:
    """Build a pending repository model with optional overrides."""
    values = {
        "user_id": uuid.uuid4(),
        "name": "openai-python",
        "repository_url": "https://github.com/openai/openai-python.git",
        "owner": "openai",
        "encrypted_token": encrypt_repository_token("secret-token"),
        "status": GitRepositoryStatus.pending,
    }
    values.update(updates)
    return GitRepository(**values)


def make_weaviate_resources() -> WeaviateResources:
    """Build placeholder shared resources for service tests."""
    return WeaviateResources(client=object(), vector_store=object())


def test_create_persists_pending_repository_and_enqueues_worker() -> None:
    """Persist canonical repository data and enqueue background work."""
    store = FakeRepositoryStore()
    tasks = BackgroundTasks()
    user_id = uuid.uuid4()
    weaviate_resources = make_weaviate_resources()

    repository = RepositoryService(store).repository_create(
        repo_url="git@github.com:openai/openai-python.git",
        token="secret-token",
        token_expiration_days=None,
        user_id=user_id,
        background_tasks=tasks,
        weaviate_resources=weaviate_resources,
    )

    assert repository.repository_url == ("https://github.com/openai/openai-python.git")
    assert repository.status == GitRepositoryStatus.pending
    assert repository.token_expiration_date is None
    assert repository.encrypted_token != "secret-token"
    assert decrypt_repository_token(repository.encrypted_token or "") == ("secret-token")
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args == (repository.id, weaviate_resources)


def test_create_rejects_equivalent_existing_repository() -> None:
    """Reject SSH and HTTPS forms of the same existing repository."""
    existing = make_repository()
    store = FakeRepositoryStore(existing)

    with pytest.raises(HTTPException) as exc_info:
        RepositoryService(store).repository_create(
            repo_url="git@github.com:openai/openai-python.git",
            token="secret-token",
            token_expiration_days=30,
            user_id=existing.user_id,
            background_tasks=BackgroundTasks(),
            weaviate_resources=make_weaviate_resources(),
        )

    assert exc_info.value.status_code == 409


def test_create_rejects_unsupported_repository_provider() -> None:
    """Reject repository hosts outside the provider allowlist."""
    store = FakeRepositoryStore()

    with pytest.raises(HTTPException) as exc_info:
        RepositoryService(store).repository_create(
            repo_url="https://example.com/team/repository.git",
            token="secret-token",
            token_expiration_days=None,
            user_id=uuid.uuid4(),
            background_tasks=BackgroundTasks(),
            weaviate_resources=make_weaviate_resources(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Repository provider is not supported"
    assert store.saved == []


def test_process_repository_follows_successful_status_sequence(monkeypatch, tmp_path: Path) -> None:
    """Clone and index a repository through the successful statuses."""
    repository = make_repository()
    store = FakeRepositoryStore(repository)

    class SessionContext:
        """Provide a context-managed fake database session."""

        def __enter__(self):
            """Return a fake session."""
            return FakeSession()

        def __exit__(self, *args):
            """Leave the context without suppressing exceptions."""
            return False

    class FakeGit:
        """Validate cloning inputs and expose repository metadata."""

        def __init__(self, parsed_url, user_id):
            """Validate the parsed URL and repository owner."""
            assert user_id == repository.user_id
            assert isinstance(parsed_url, ParsedRepositoryUrl)
            assert parsed_url.canonical_url == repository.repository_url
            self.repo_path = tmp_path

        def clone(self, token):
            """Validate the decrypted clone token."""
            assert token == "secret-token"

        def get_default_branch(self):
            """Return the repository's default branch."""
            return "main"

    class FakeIngestor:
        """Validate repository ingestion arguments."""

        def __init__(self, resources):
            """Validate the shared Weaviate resources."""
            assert resources is weaviate_resources

        def ingest(self, repo_path, repository_id, branch, user_id):
            """Validate the repository indexing request."""
            assert (repo_path, repository_id, branch, user_id) == (tmp_path, repository.id, "main", repository.user_id)

    monkeypatch.setattr(git_repository_service, "Session", lambda engine: SessionContext())
    monkeypatch.setattr(git_repository_service, "GitRepositoryRepository", lambda session: store)
    monkeypatch.setattr(git_repository_service, "GitCommands", FakeGit)
    weaviate_resources = make_weaviate_resources()
    monkeypatch.setattr(git_repository_service, "DocumentIngestor", FakeIngestor)

    git_repository_service.process_repository(repository.id, weaviate_resources)

    assert store.statuses == [GitRepositoryStatus.cloning, GitRepositoryStatus.cloned, GitRepositoryStatus.indexing, GitRepositoryStatus.ready]
    assert repository.default_branch == "main"
    assert repository.local_path == str(tmp_path)


def test_process_repository_marks_failure_without_persisting_token(monkeypatch) -> None:
    """Redact repository credentials from persisted clone failures."""
    token = "secret-token"
    repository = make_repository(encrypted_token=encrypt_repository_token(token))
    store = FakeRepositoryStore(repository)

    class SessionContext:
        """Provide a context-managed fake database session."""

        def __enter__(self):
            """Return a fake session."""
            return FakeSession()

        def __exit__(self, *args):
            """Leave the context without suppressing exceptions."""
            return False

    class FailingGit:
        """Raise a clone error containing the supplied credential."""

        def __init__(self, parsed_url, user_id):
            """Validate the parsed URL and repository owner."""
            assert user_id == repository.user_id
            assert isinstance(parsed_url, ParsedRepositoryUrl)
            assert parsed_url.canonical_url == repository.repository_url

        def clone(self, received_token):
            """Raise an authentication error containing the token."""
            raise GitError(f"Authentication failed for {received_token}")

    monkeypatch.setattr(git_repository_service, "Session", lambda engine: SessionContext())
    monkeypatch.setattr(git_repository_service, "GitRepositoryRepository", lambda session: store)
    monkeypatch.setattr(git_repository_service, "GitCommands", FailingGit)

    git_repository_service.process_repository(repository.id, make_weaviate_resources())

    assert repository.status == GitRepositoryStatus.failed
    assert token not in (repository.failed_reason or "")
    assert "[REDACTED]" in (repository.failed_reason or "")


def test_expired_token_fails_before_clone(monkeypatch) -> None:
    """Mark repositories with expired credentials as failed."""
    repository = make_repository(token_expiration_date=datetime.now(UTC) - timedelta(days=1))
    store = FakeRepositoryStore(repository)

    class SessionContext:
        """Provide a context-managed fake database session."""

        def __enter__(self):
            """Return a fake session."""
            return FakeSession()

        def __exit__(self, *args):
            """Leave the context without suppressing exceptions."""
            return False

    monkeypatch.setattr(git_repository_service, "Session", lambda engine: SessionContext())
    monkeypatch.setattr(git_repository_service, "GitRepositoryRepository", lambda session: store)

    git_repository_service.process_repository(repository.id, make_weaviate_resources())

    assert repository.status == GitRepositoryStatus.failed
    assert repository.failed_reason == "Repository token has expired"
