"""Test Git repository service workflows with injected collaborators."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core.security import decrypt_repository_token, encrypt_repository_token
from app.core.vector_db import WeaviateResources
from app.enums.repository import RepositoryStatus
from app.errors.git_errors import GitError
from app.git.repository_url import ParsedRepositoryUrl
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryCreate, RepositoryUpdate
from app.services.repository_service import RepositoryService


class FakeRepositoryStore:
    """Store one Git repository and record persistence operations."""

    def __init__(self, repository: Repository | None = None):
        self.repository = repository
        self.saved: list[Repository] = []
        self.statuses: list[RepositoryStatus] = []
        self.deleted: list[Repository] = []
        self.rolled_back = False

    def get_by_url_and_user_id(self, repository_url, user_id):
        if self.repository and self.repository.repository_url == repository_url and self.repository.user_id == user_id:
            return self.repository
        return None

    def get_by_user_id(self, user_id):
        if self.repository and self.repository.user_id == user_id:
            return [self.repository]
        return []

    def get_by_id(self, repository_id):
        if self.repository and self.repository.id == repository_id:
            return self.repository
        return None

    def get_page(self, *, skip, limit, user_id=None):
        repositories = self.get_by_user_id(user_id) if user_id else ([self.repository] if self.repository else [])
        return repositories[skip : skip + limit]

    def count(self, *, user_id=None):
        return len(self.get_page(skip=0, limit=100, user_id=user_id))

    def save(self, repository):
        self.repository = repository
        self.saved.append(repository)
        return repository

    def update_token(self, repository, *, encrypted_token, token_expiration_date):
        repository.encrypted_token = encrypted_token
        repository.token_expiration_date = token_expiration_date
        return self.save(repository)

    def delete(self, repository):
        self.deleted.append(repository)
        self.repository = None

    def rollback(self):
        self.rolled_back = True

    def update_status(self, repository, status, *, failed_reason=None):
        repository.status = status
        repository.failed_reason = failed_reason
        self.statuses.append(status)
        return repository


class FakeIngestor:
    """Record Git repository ingestion and deletion calls."""

    def __init__(self):
        self.ingest_calls = []
        self.delete_calls = []
        self.delete_error: Exception | None = None

    def ingest(self, repo_path, repository_id, branch, user_id):
        self.ingest_calls.append((repo_path, repository_id, branch, user_id))

    def delete_by_repository(self, repository_id, *, user_id):
        if self.delete_error:
            raise self.delete_error
        self.delete_calls.append((repository_id, user_id))


def make_service(store: FakeRepositoryStore, *, ingestor: FakeIngestor | None = None, git_factory=object) -> RepositoryService:
    """Build a service from explicit test doubles."""
    return RepositoryService(store, ingestor or FakeIngestor(), git_factory)


def make_repository(**updates: Any) -> Repository:
    """Build a pending Git repository model with optional overrides."""
    values = {
        "user_id": uuid.uuid4(),
        "name": "openai-python",
        "repository_url": "https://github.com/openai/openai-python.git",
        "owner": "openai",
        "encrypted_token": encrypt_repository_token("secret-token"),
        "status": RepositoryStatus.pending,
    }
    values.update(updates)
    return Repository(**values)


def make_user(*, user_id: uuid.UUID | None = None, is_superuser: bool = False) -> User:
    """Build an authenticated service-layer user."""
    resolved_id = user_id or uuid.uuid4()
    return User(id=resolved_id, email=f"{resolved_id}@example.com", hashed_password="not-used", is_superuser=is_superuser)


def make_weaviate_resources() -> WeaviateResources:
    """Build placeholder shared resources for background task assertions."""
    return WeaviateResources(client=object(), vector_store=object())


def test_create_persists_pending_repository_and_enqueues_worker() -> None:
    store = FakeRepositoryStore()
    tasks = BackgroundTasks()
    user_id = uuid.uuid4()
    user = make_user(user_id=user_id)
    weaviate_resources = make_weaviate_resources()

    repository = make_service(store).create_repository(
        repository_in=RepositoryCreate(repository_url="git@github.com:openai/openai-python.git", token="secret-token", token_expiration_days=None),
        user=user,
        background_tasks=tasks,
        weaviate_resources=weaviate_resources,
    )

    assert repository.repository_url == ("https://github.com/openai/openai-python.git")
    assert repository.status == RepositoryStatus.pending
    assert repository.token_expiration_date is None
    assert decrypt_repository_token(repository.encrypted_token or "") == ("secret-token")
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args == (repository.id, "secret-token", weaviate_resources)


def test_create_rejects_equivalent_existing_repository() -> None:
    existing = make_repository()
    store = FakeRepositoryStore(existing)

    with pytest.raises(HTTPException) as exc_info:
        make_service(store).create_repository(
            repository_in=RepositoryCreate(repository_url="git@github.com:openai/openai-python.git", token="secret-token", token_expiration_days=30),
            user=make_user(user_id=existing.user_id),
            background_tasks=BackgroundTasks(),
            weaviate_resources=make_weaviate_resources(),
        )

    assert exc_info.value.status_code == 409


def test_create_rejects_unsupported_repository_provider() -> None:
    store = FakeRepositoryStore()

    with pytest.raises(HTTPException) as exc_info:
        make_service(store).create_repository(
            repository_in=RepositoryCreate(repository_url="https://example.com/team/repository.git", token="secret-token", token_expiration_days=None),
            user=make_user(),
            background_tasks=BackgroundTasks(),
            weaviate_resources=make_weaviate_resources(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Repository provider is not supported"
    assert store.saved == []


def test_process_repository_follows_successful_status_sequence(tmp_path: Path) -> None:
    repository = make_repository()
    store = FakeRepositoryStore(repository)

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            assert user_id == repository.user_id
            assert isinstance(parsed_url, ParsedRepositoryUrl)
            assert parsed_url.canonical_url == repository.repository_url
            self.repo_path = tmp_path

        def clone(self, token):
            assert token == "secret-token"

        def get_default_branch(self):
            return "main"

    ingestor = FakeIngestor()
    make_service(store, ingestor=ingestor, git_factory=FakeGit).process_repository(repository.id, "secret-token")

    assert store.statuses == [RepositoryStatus.cloning, RepositoryStatus.cloned, RepositoryStatus.indexing, RepositoryStatus.ready]
    assert repository.default_branch == "main"
    assert repository.local_path == str(tmp_path)
    assert ingestor.ingest_calls == [(tmp_path, repository.id, "main", repository.user_id)]


def test_process_repository_marks_failure_without_persisting_token() -> None:
    token = "secret-token"
    repository = make_repository(encrypted_token=encrypt_repository_token(token))
    store = FakeRepositoryStore(repository)

    class FailingGit:
        def __init__(self, parsed_url, user_id):
            assert user_id == repository.user_id

        def clone(self, received_token):
            raise GitError(f"Authentication failed for {received_token}")

    make_service(store, git_factory=FailingGit).process_repository(repository.id, token)

    assert repository.status == RepositoryStatus.failed
    assert token not in (repository.failed_reason or "")
    assert "[REDACTED]" in (repository.failed_reason or "")
    assert store.rolled_back


def test_process_repository_uses_caller_supplied_token(tmp_path: Path) -> None:
    repository = make_repository(encrypted_token=None, token_expiration_date=datetime.now(UTC) - timedelta(days=1))
    store = FakeRepositoryStore(repository)

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            self.repo_path = tmp_path

        def clone(self, token):
            assert token == "caller-token"

        def get_default_branch(self):
            return "main"

    make_service(store, git_factory=FakeGit).process_repository(repository.id, "caller-token")

    assert repository.status == RepositoryStatus.ready


def test_update_replaces_only_encrypted_credentials() -> None:
    repository = make_repository(status=RepositoryStatus.ready, default_branch="main")
    store = FakeRepositoryStore(repository)

    make_service(store).update_repository(
        repository_id=repository.id,
        repository_in=RepositoryUpdate(token="replacement-token", token_expiration_days=7),
        user=make_user(user_id=repository.user_id),
    )

    assert decrypt_repository_token(repository.encrypted_token or "") == ("replacement-token")
    assert repository.token_expiration_date is not None
    assert repository.token_expiration_date > datetime.now(UTC) + timedelta(days=6)
    assert repository.status == RepositoryStatus.ready
    assert repository.default_branch == "main"


def test_update_with_null_expiration_clears_expiration() -> None:
    repository = make_repository(token_expiration_date=datetime.now(UTC) + timedelta(days=1))
    store = FakeRepositoryStore(repository)

    make_service(store).update_repository(
        repository_id=repository.id,
        repository_in=RepositoryUpdate(token="replacement-token", token_expiration_days=None),
        user=make_user(user_id=repository.user_id),
    )

    assert repository.token_expiration_date is None


@pytest.mark.parametrize("repository_status", [RepositoryStatus.pending, RepositoryStatus.cloning, RepositoryStatus.cloned, RepositoryStatus.indexing])
def test_delete_rejects_active_processing_states(repository_status) -> None:
    repository = make_repository(status=repository_status)
    store = FakeRepositoryStore(repository)

    with pytest.raises(HTTPException) as exc_info:
        make_service(store).delete_repository(repository_id=repository.id, user=make_user(user_id=repository.user_id))

    assert exc_info.value.status_code == 409
    assert store.deleted == []


def test_delete_cleans_local_vector_and_database_state_in_order() -> None:
    repository = make_repository(status=RepositoryStatus.ready)
    store = FakeRepositoryStore(repository)
    calls = []

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            assert parsed_url.canonical_url == repository.repository_url
            assert user_id == repository.user_id

        def delete_checkout(self):
            calls.append("local")

    class OrderedIngestor(FakeIngestor):
        def delete_by_repository(self, repository_id, *, user_id):
            calls.append("vector")
            super().delete_by_repository(repository_id, user_id=user_id)

    original_delete = store.delete

    def delete(repository_to_delete):
        calls.append("database")
        original_delete(repository_to_delete)

    store.delete = delete
    ingestor = OrderedIngestor()

    make_service(store, ingestor=ingestor, git_factory=FakeGit).delete_repository(repository_id=repository.id, user=make_user(user_id=repository.user_id))

    assert calls == ["local", "vector", "database"]
    assert ingestor.delete_calls == [(repository.id, repository.user_id)]
    assert store.deleted == [repository]


def test_vector_cleanup_failure_preserves_database_record() -> None:
    repository = make_repository(status=RepositoryStatus.failed)
    store = FakeRepositoryStore(repository)
    ingestor = FakeIngestor()
    ingestor.delete_error = RuntimeError("weaviate unavailable")

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            pass

        def delete_checkout(self):
            pass

    with pytest.raises(RuntimeError, match="weaviate unavailable"):
        make_service(store, ingestor=ingestor, git_factory=FakeGit).delete_repository(repository_id=repository.id, user=make_user(user_id=repository.user_id))

    assert store.repository is repository
    assert store.deleted == []


def test_repository_access_enforces_owner_and_allows_superuser() -> None:
    repository = make_repository(status=RepositoryStatus.ready)
    service = make_service(FakeRepositoryStore(repository))

    with pytest.raises(HTTPException) as exc_info:
        service.get_repository(repository_id=repository.id, user=make_user())
    assert exc_info.value.status_code == 403

    assert service.get_repository(repository_id=repository.id, user=make_user(is_superuser=True)) is repository
