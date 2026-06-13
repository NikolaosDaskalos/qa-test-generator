"""Test Git repository route contracts with dependency overrides."""

import uuid
from types import SimpleNamespace

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.routes.repositories import create_repository, read_repositories, read_repository, router
from app.core.vector_db import get_weaviate_resources
from app.dependencies import get_current_user, get_repository_service
from app.enums.repository import RepositoryStatus
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate


class FakeRepositoryService:
    """Record mutation endpoint calls."""

    def __init__(self, repository: Repository | None = None) -> None:
        self.repository = repository
        self.list_calls = []
        self.get_calls = []
        self.create_calls = []
        self.update_calls = []
        self.delete_calls = []

    def list_repositories(self, **kwargs):
        self.list_calls.append(kwargs)
        return {"data": [], "count": 0}

    def get_repository(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.repository

    def create_repository(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.repository

    def update_repository(self, **kwargs) -> None:
        self.update_calls.append(kwargs)

    def delete_repository(self, **kwargs) -> None:
        self.delete_calls.append(kwargs)


def _client(repository_service: FakeRepositoryService, user_id: uuid.UUID) -> tuple[TestClient, SimpleNamespace]:
    app = FastAPI()
    app.include_router(router)
    user = SimpleNamespace(id=user_id, is_superuser=False)
    app.dependency_overrides[get_repository_service] = lambda: repository_service
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_weaviate_resources] = object
    return TestClient(app), user


def test_read_repositories_passes_user_object() -> None:
    """Pass the authenticated user intact to list orchestration."""
    repository_service = FakeRepositoryService()
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)

    read_repositories(repository_service, user, skip=10, limit=20)

    assert repository_service.list_calls == [{"user": user, "skip": 10, "limit": 20}]


def test_read_repository_passes_user_object() -> None:
    """Pass the authenticated user intact to get orchestration."""
    repository_service = FakeRepositoryService()
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository_id = uuid.uuid4()

    read_repository(repository_service, user, repository_id)

    assert repository_service.get_calls == [{"repository_id": repository_id, "user": user}]


def test_read_repository_exposes_failed_status_without_credential() -> None:
    user_id = uuid.uuid4()
    repository = Repository(
        user_id=user_id,
        name="openai-python",
        repository_url="https://github.com/openai/openai-python.git",
        owner="openai",
        status=RepositoryStatus.failed,
        encrypted_token="encrypted-secret",
        failed_reason="Authentication failed",
    )
    client, _ = _client(FakeRepositoryService(repository), user_id)

    with client:
        response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failed_reason"] == "Authentication failed"
    assert "encrypted_token" not in response.json()


def test_read_repository_exposes_fetch_ready_checkout_information() -> None:
    user_id = uuid.uuid4()
    repository = Repository(
        user_id=user_id,
        name="openai-python",
        repository_url="https://github.com/openai/openai-python.git",
        owner="openai",
        status=RepositoryStatus.ready,
        default_branch="main",
        indexed_commit_sha="a" * 40,
        local_path="/private/checkouts/openai-python",
    )
    client, _ = _client(FakeRepositoryService(repository), user_id)

    with client:
        response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 200
    assert response.json()["default_branch"] == "main"
    assert response.json()["indexed_commit_sha"] == "a" * 40
    assert "local_path" not in response.json()


def test_create_repository_passes_request_and_user_objects() -> None:
    """Pass validated create input and user intact to the service."""
    repository_service = FakeRepositoryService()
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository_in = RepositoryCreate(repository_url="https://github.com/openai/openai-python.git", token="secret-token", token_expiration_days=30)
    background_tasks = BackgroundTasks()
    resources = object()

    create_repository(
        repository_service=repository_service, current_user=user, weaviate_resources=resources, background_tasks=background_tasks, repository_in=repository_in
    )

    assert repository_service.create_calls == [
        {"repository_in": repository_in, "user": user, "background_tasks": background_tasks, "weaviate_resources": resources}
    ]


def test_create_repository_returns_accepted_pending_response_without_credential() -> None:
    user_id = uuid.uuid4()
    repository = Repository(
        user_id=user_id,
        name="openai-python",
        repository_url="https://github.com/openai/openai-python.git",
        owner="openai",
        status=RepositoryStatus.pending,
        encrypted_token="encrypted-secret",
    )
    client, _ = _client(FakeRepositoryService(repository), user_id)

    with client:
        response = client.post("/repositories/", json={"repository_url": "git@github.com:openai/openai-python.git", "token": "secret-token"})

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["repository_url"] == "https://github.com/openai/openai-python.git"
    assert "encrypted_token" not in response.json()
    assert "token" not in response.json()


def test_create_repository_requires_authentication() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_service] = FakeRepositoryService
    app.dependency_overrides[get_weaviate_resources] = object

    with TestClient(app) as client:
        response = client.post("/repositories/", json={"repository_url": "https://github.com/openai/openai-python.git", "token": "secret-token"})

    assert response.status_code == 401


def test_update_repository_returns_empty_204() -> None:
    """Expose the credential update as an empty successful response."""
    repository_service = FakeRepositoryService()
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    client, user = _client(repository_service, user_id)
    with client:
        response = client.put(f"/repositories/{repository_id}", json={"token": "replacement-token", "token_expiration_days": None})

    assert response.status_code == 204
    assert response.content == b""
    assert len(repository_service.update_calls) == 1
    call = repository_service.update_calls[0]
    assert call["repository_id"] == repository_id
    assert call["repository_in"].token == "replacement-token"
    assert call["repository_in"].token_expiration_days is None
    assert call["user"] is user


def test_delete_repository_returns_empty_204() -> None:
    """Expose coordinated deletion as an empty successful response."""
    repository_service = FakeRepositoryService()
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    client, user = _client(repository_service, user_id)
    with client:
        response = client.delete(f"/repositories/{repository_id}")

    assert response.status_code == 204
    assert repository_service.delete_calls == [{"repository_id": repository_id, "user": user}]


def test_delete_repository_returns_500_when_synchronous_cleanup_fails() -> None:
    """Report cleanup failure from the synchronous delete request."""

    class FailingRepositoryService(FakeRepositoryService):
        def delete_repository(self, **kwargs) -> None:
            super().delete_repository(**kwargs)
            raise HTTPException(status_code=500, detail="Repository deletion failed")

    repository_service = FailingRepositoryService()
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    client, user = _client(repository_service, user_id)
    with client:
        response = client.delete(f"/repositories/{repository_id}")

    assert response.status_code == 500
    assert response.json() == {"detail": "Repository deletion failed"}
    assert repository_service.delete_calls == [{"repository_id": repository_id, "user": user}]
