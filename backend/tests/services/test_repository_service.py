"""Test Git repository service workflows with injected collaborators."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core.security import decrypt_repository_token, encrypt_repository_token
from app.core.vector_db import WeaviateResources
from app.enums.repository import RepositoryProvider, RepositoryStatus
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

    def begin_cloning(self, repository):
        repository.status = RepositoryStatus.cloning
        repository.failed_reason = None
        self.statuses.append(RepositoryStatus.cloning)
        return repository

    def record_checkout(self, repository, *, local_path, default_branch):
        repository.local_path = local_path
        repository.default_branch = default_branch
        return repository

    def begin_indexing(self, repository):
        repository.status = RepositoryStatus.indexing
        self.statuses.append(RepositoryStatus.indexing)
        return repository

    def fail(self, repository, exc, *, credential, fallback="Repository processing failed"):
        reason = str(exc) if isinstance(exc, (GitError, ValueError)) else fallback
        if credential:
            reason = reason.replace(credential, "[REDACTED]")
        reason = reason[:1000]
        repository.status = RepositoryStatus.failed
        repository.failed_reason = reason
        self.statuses.append(RepositoryStatus.failed)
        return reason

    def mark_ready(self, repository, *, indexed_commit_sha):
        repository.indexed_commit_sha = indexed_commit_sha
        repository.status = RepositoryStatus.ready
        repository.failed_reason = None
        self.statuses.append(RepositoryStatus.ready)
        return repository


class FakeIngestor:
    """Record Git repository ingestion and deletion calls."""

    def __init__(self):
        self.ingest_calls = []
        self.ingest_error: Exception | None = None
        self.chunk_count = 1
        self.delete_calls = []
        self.delete_error: Exception | None = None

    def ingest(self, repo_path, repository_id, branch, commit_sha, user_id):
        self.ingest_calls.append((repo_path, repository_id, branch, commit_sha, user_id))
        if self.ingest_error:
            raise self.ingest_error
        return self.chunk_count

    def delete_repository(self, repository_id, *, user_id):
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
    assert repository.provider == RepositoryProvider.github
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
    git_calls = []

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

        def checkout(self, branch):
            git_calls.append(("checkout", branch))

        def get_current_commit_sha(self):
            assert git_calls == [("checkout", "main")]
            return "a" * 40

    ingestor = FakeIngestor()
    make_service(store, ingestor=ingestor, git_factory=FakeGit).process_repository(repository.id, "secret-token")

    assert store.statuses == [RepositoryStatus.cloning, RepositoryStatus.indexing, RepositoryStatus.ready]
    assert repository.default_branch == "main"
    assert repository.local_path == str(tmp_path)
    assert repository.indexed_commit_sha == "a" * 40
    assert ingestor.ingest_calls == [(tmp_path, repository.id, "main", "a" * 40, repository.user_id)]


def test_process_repository_rejects_repository_without_python_chunks(tmp_path: Path) -> None:
    """Do not make unsupported Repository Evidence available."""
    repository = make_repository()
    store = FakeRepositoryStore(repository)
    ingestor = FakeIngestor()
    ingestor.chunk_count = 0

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            self.repo_path = tmp_path

        def clone(self, token):
            pass

        def get_default_branch(self):
            return "main"

        def checkout(self, branch):
            assert branch == "main"

        def get_current_commit_sha(self):
            return "a" * 40

    make_service(store, ingestor=ingestor, git_factory=FakeGit).process_repository(repository.id, "secret-token")

    assert repository.status == RepositoryStatus.failed
    assert repository.failed_reason == "Repository contains no usable Python files"
    assert repository.indexed_commit_sha is None


def test_process_repository_marks_failure_without_exposing_token(caplog) -> None:
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
    assert token not in caplog.text
    assert store.rolled_back


def test_process_repository_does_not_advance_indexed_commit_when_ingestion_fails(tmp_path: Path) -> None:
    repository = make_repository()
    store = FakeRepositoryStore(repository)
    ingestor = FakeIngestor()
    ingestor.ingest_error = RuntimeError("index unavailable")

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            self.repo_path = tmp_path

        def clone(self, token):
            pass

        def get_default_branch(self):
            return "main"

        def checkout(self, branch):
            assert branch == "main"

        def get_current_commit_sha(self):
            return "a" * 40

    make_service(store, ingestor=ingestor, git_factory=FakeGit).process_repository(repository.id, "secret-token")

    assert repository.status == RepositoryStatus.failed
    assert repository.indexed_commit_sha is None
    assert ingestor.ingest_calls == [(tmp_path, repository.id, "main", "a" * 40, repository.user_id)]


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

        def checkout(self, branch):
            assert branch == "main"

        def get_current_commit_sha(self):
            return "b" * 40

    make_service(store, git_factory=FakeGit).process_repository(repository.id, "caller-token")

    assert repository.status == RepositoryStatus.ready


def test_update_replaces_only_encrypted_credentials() -> None:
    repository = make_repository(status=RepositoryStatus.ready, default_branch="main")
    store = FakeRepositoryStore(repository)
    calls = []

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            assert parsed_url.canonical_url == repository.repository_url
            assert user_id == repository.user_id

        def validate_remote_access(self, token):
            calls.append(("validate", token))

    original_update_token = store.update_token

    def update_token(*args, **kwargs):
        calls.append(("persist", decrypt_repository_token(kwargs["encrypted_token"])))
        return original_update_token(*args, **kwargs)

    store.update_token = update_token

    make_service(store, git_factory=FakeGit).update_repository(
        repository_id=repository.id,
        repository_in=RepositoryUpdate(token="replacement-token", token_expiration_days=7),
        user=make_user(user_id=repository.user_id),
    )

    assert calls == [("validate", "replacement-token"), ("persist", "replacement-token")]
    assert decrypt_repository_token(repository.encrypted_token or "") == ("replacement-token")
    assert repository.token_expiration_date is not None
    assert repository.token_expiration_date > datetime.now(UTC) + timedelta(days=6)
    assert repository.status == RepositoryStatus.ready
    assert repository.default_branch == "main"


def test_update_with_null_expiration_clears_expiration() -> None:
    repository = make_repository(token_expiration_date=datetime.now(UTC) + timedelta(days=1))
    store = FakeRepositoryStore(repository)

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            pass

        def validate_remote_access(self, token):
            pass

    make_service(store, git_factory=FakeGit).update_repository(
        repository_id=repository.id,
        repository_in=RepositoryUpdate(token="replacement-token", token_expiration_days=None),
        user=make_user(user_id=repository.user_id),
    )

    assert repository.token_expiration_date is None


def test_update_rejects_token_without_repository_access() -> None:
    repository = make_repository(token_expiration_date=datetime.now(UTC) + timedelta(days=1))
    original_encrypted_token = repository.encrypted_token
    original_expiration = repository.token_expiration_date
    store = FakeRepositoryStore(repository)

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            pass

        def validate_remote_access(self, token):
            raise GitError(f"Authentication failed for {token}")

    with pytest.raises(HTTPException) as exc_info:
        make_service(store, git_factory=FakeGit).update_repository(
            repository_id=repository.id,
            repository_in=RepositoryUpdate(token="invalid-token", token_expiration_days=30),
            user=make_user(user_id=repository.user_id),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token is invalid for repository"
    assert repository.encrypted_token == original_encrypted_token
    assert repository.token_expiration_date == original_expiration
    assert store.saved == []


@pytest.mark.parametrize("repository_status", [RepositoryStatus.pending, RepositoryStatus.cloning, RepositoryStatus.indexing])
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
        def delete_repository(self, repository_id, *, user_id):
            calls.append("vector")
            super().delete_repository(repository_id, user_id=user_id)

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


def test_local_cleanup_failure_persists_failure_and_returns_500() -> None:
    credential = "secret-token"
    repository = make_repository(status=RepositoryStatus.ready, encrypted_token=credential)
    store = FakeRepositoryStore(repository)
    ingestor = FakeIngestor()

    class FailingGit:
        def __init__(self, parsed_url, user_id):
            pass

        def delete_checkout(self):
            raise GitError(f"Checkout deletion failed for credential {credential}: " + ("x" * 1100))

    with pytest.raises(HTTPException) as exc_info:
        make_service(store, ingestor=ingestor, git_factory=FailingGit).delete_repository(
            repository_id=repository.id, user=make_user(user_id=repository.user_id)
        )

    assert exc_info.value.status_code == 500
    assert repository.status == RepositoryStatus.failed
    assert repository.failed_reason.startswith("Checkout deletion failed for credential [REDACTED]")
    assert credential not in repository.failed_reason
    assert len(repository.failed_reason) == 1000
    assert ingestor.delete_calls == []
    assert store.repository is repository
    assert store.deleted == []


def test_vector_cleanup_failure_persists_failure_and_returns_500() -> None:
    repository = make_repository(status=RepositoryStatus.ready)
    store = FakeRepositoryStore(repository)
    ingestor = FakeIngestor()
    ingestor.delete_error = RuntimeError("weaviate unavailable")
    local_deleted = False

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            pass

        def delete_checkout(self):
            nonlocal local_deleted
            local_deleted = True

    with pytest.raises(HTTPException) as exc_info:
        make_service(store, ingestor=ingestor, git_factory=FakeGit).delete_repository(repository_id=repository.id, user=make_user(user_id=repository.user_id))

    assert exc_info.value.status_code == 500
    assert local_deleted
    assert repository.status == RepositoryStatus.failed
    assert repository.failed_reason == "Repository vector deletion failed"
    assert "weaviate" not in repository.failed_reason.lower()
    assert store.repository is repository
    assert store.deleted == []


def test_database_cleanup_failure_rolls_back_reloads_and_persists_failure() -> None:
    repository = make_repository(status=RepositoryStatus.ready)

    class FailingDeleteStore(FakeRepositoryStore):
        def __init__(self, stored_repository):
            super().__init__(stored_repository)
            self.transaction_calls = []
            self.get_calls = 0

        def get_by_id(self, repository_id):
            self.get_calls += 1
            if self.get_calls > 1:
                self.transaction_calls.append("reload")
            return super().get_by_id(repository_id)

        def delete(self, repository_to_delete):
            self.transaction_calls.append("delete")
            raise RuntimeError("psycopg commit details")

        def rollback(self):
            self.transaction_calls.append("rollback")
            super().rollback()

        def fail(self, repository_to_update, exc, *, credential, fallback="Repository processing failed"):
            self.transaction_calls.append("persist_failed")
            return super().fail(repository_to_update, exc, credential=credential, fallback=fallback)

    store = FailingDeleteStore(repository)

    class FakeGit:
        def __init__(self, parsed_url, user_id):
            pass

        def delete_checkout(self):
            pass

    with pytest.raises(HTTPException) as exc_info:
        make_service(store, git_factory=FakeGit).delete_repository(repository_id=repository.id, user=make_user(user_id=repository.user_id))

    assert exc_info.value.status_code == 500
    assert store.transaction_calls == ["delete", "rollback", "reload", "persist_failed"]
    assert repository.status == RepositoryStatus.failed
    assert repository.failed_reason == "Repository database deletion failed"
    assert "psycopg" not in repository.failed_reason.lower()


def test_repository_access_enforces_owner_and_allows_superuser() -> None:
    repository = make_repository(status=RepositoryStatus.ready)
    service = make_service(FakeRepositoryStore(repository))

    assert service.get_repository(repository_id=repository.id, user=make_user(user_id=repository.user_id)) is repository

    with pytest.raises(HTTPException) as exc_info:
        service.get_repository(repository_id=repository.id, user=make_user())
    assert exc_info.value.status_code == 403

    assert service.get_repository(repository_id=repository.id, user=make_user(is_superuser=True)) is repository
