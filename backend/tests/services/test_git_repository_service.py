import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core.security import decrypt_repository_token, encrypt_repository_token
from app.errors.git_errors import GitError
from app.git.repository_url import ParsedRepositoryUrl
from app.models.git_repositories import GitRepository, GitRepositoryStatus
from app.services import git_repository_service
from app.services.git_repository_service import RepositoryService


class FakeSession:
    def rollback(self) -> None:
        pass


class FakeRepositoryStore:
    def __init__(self, repository: GitRepository | None = None):
        self.session = FakeSession()
        self.repository = repository
        self.saved: list[GitRepository] = []
        self.statuses: list[GitRepositoryStatus] = []

    def get_by_url_and_user_id(self, repository_url, user_id):
        if (
            self.repository
            and self.repository.repository_url == repository_url
            and self.repository.user_id == user_id
        ):
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

    def save(self, repository):
        self.repository = repository
        self.saved.append(repository)
        return repository

    def update_status(self, repository, status, *, failed_reason=None):
        repository.status = status
        repository.failed_reason = failed_reason
        self.statuses.append(status)
        return repository


def make_repository(**updates: Any) -> GitRepository:
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


def test_create_persists_pending_repository_and_enqueues_worker() -> None:
    store = FakeRepositoryStore()
    tasks = BackgroundTasks()
    user_id = uuid.uuid4()

    repository = RepositoryService(store).repository_create(
        repo_url="git@github.com:openai/openai-python.git",
        token="secret-token",
        token_expiration_days=None,
        user_id=user_id,
        background_tasks=tasks,
    )

    assert repository.repository_url == ("https://github.com/openai/openai-python.git")
    assert repository.status == GitRepositoryStatus.pending
    assert repository.token_expiration_date is None
    assert repository.encrypted_token != "secret-token"
    assert decrypt_repository_token(repository.encrypted_token or "") == (
        "secret-token"
    )
    assert len(tasks.tasks) == 1


def test_create_rejects_equivalent_existing_repository() -> None:
    existing = make_repository()
    store = FakeRepositoryStore(existing)

    with pytest.raises(HTTPException) as exc_info:
        RepositoryService(store).repository_create(
            repo_url="git@github.com:openai/openai-python.git",
            token="secret-token",
            token_expiration_days=30,
            user_id=existing.user_id,
            background_tasks=BackgroundTasks(),
        )

    assert exc_info.value.status_code == 409


def test_create_rejects_unsupported_repository_provider() -> None:
    store = FakeRepositoryStore()

    with pytest.raises(HTTPException) as exc_info:
        RepositoryService(store).repository_create(
            repo_url="https://example.com/team/repository.git",
            token="secret-token",
            token_expiration_days=None,
            user_id=uuid.uuid4(),
            background_tasks=BackgroundTasks(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Repository provider is not supported"
    assert store.saved == []


def test_process_repository_follows_successful_status_sequence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = make_repository()
    store = FakeRepositoryStore(repository)

    class SessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *args):
            return False

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

    class FakeIngestor:
        def ingest(self, repo_path, repository_id, branch):
            assert (repo_path, repository_id, branch) == (
                tmp_path,
                repository.id,
                "main",
            )

    monkeypatch.setattr(
        git_repository_service, "Session", lambda engine: SessionContext()
    )
    monkeypatch.setattr(
        git_repository_service,
        "GitRepositoryRepository",
        lambda session: store,
    )
    monkeypatch.setattr(git_repository_service, "GitCommands", FakeGit)
    monkeypatch.setattr(
        git_repository_service,
        "build_document_ingestor",
        FakeIngestor,
    )

    git_repository_service.process_repository(repository.id)

    assert store.statuses == [
        GitRepositoryStatus.cloning,
        GitRepositoryStatus.cloned,
        GitRepositoryStatus.indexing,
        GitRepositoryStatus.ready,
    ]
    assert repository.default_branch == "main"
    assert repository.local_path == str(tmp_path)


def test_process_repository_marks_failure_without_persisting_token(
    monkeypatch,
) -> None:
    token = "secret-token"
    repository = make_repository(encrypted_token=encrypt_repository_token(token))
    store = FakeRepositoryStore(repository)

    class SessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *args):
            return False

    class FailingGit:
        def __init__(self, parsed_url, user_id):
            assert user_id == repository.user_id
            assert isinstance(parsed_url, ParsedRepositoryUrl)
            assert parsed_url.canonical_url == repository.repository_url

        def clone(self, received_token):
            raise GitError(f"Authentication failed for {received_token}")

    monkeypatch.setattr(
        git_repository_service, "Session", lambda engine: SessionContext()
    )
    monkeypatch.setattr(
        git_repository_service,
        "GitRepositoryRepository",
        lambda session: store,
    )
    monkeypatch.setattr(git_repository_service, "GitCommands", FailingGit)

    git_repository_service.process_repository(repository.id)

    assert repository.status == GitRepositoryStatus.failed
    assert token not in (repository.failed_reason or "")
    assert "[REDACTED]" in (repository.failed_reason or "")


def test_expired_token_fails_before_clone(monkeypatch) -> None:
    repository = make_repository(
        token_expiration_date=datetime.now(UTC) - timedelta(days=1)
    )
    store = FakeRepositoryStore(repository)

    class SessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        git_repository_service, "Session", lambda engine: SessionContext()
    )
    monkeypatch.setattr(
        git_repository_service,
        "GitRepositoryRepository",
        lambda session: store,
    )

    git_repository_service.process_repository(repository.id)

    assert repository.status == GitRepositoryStatus.failed
    assert repository.failed_reason == "Repository token has expired"
