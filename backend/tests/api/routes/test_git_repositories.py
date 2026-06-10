"""Test repository route contracts with dependency overrides."""

import uuid
from types import SimpleNamespace

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from app.api.routes.git_repositories import create_repository, read_repositories, read_repository, router
from app.dependencies import get_current_user, get_repository_service
from app.models.git_repositories import GitRepositoryCreate


class FakeRepositoryService:
    """Record mutation endpoint calls."""

    def __init__(self) -> None:
        self.list_calls = []
        self.get_calls = []
        self.create_calls = []
        self.update_calls = []
        self.delete_calls = []

    def repository_list(self, **kwargs):
        self.list_calls.append(kwargs)
        return {"data": [], "count": 0}

    def repository_get(self, **kwargs):
        self.get_calls.append(kwargs)
        return None

    def repository_create(self, **kwargs):
        self.create_calls.append(kwargs)
        return None

    def repository_update(self, **kwargs) -> None:
        self.update_calls.append(kwargs)

    def repository_delete(self, **kwargs) -> None:
        self.delete_calls.append(kwargs)


def _client(service: FakeRepositoryService, user_id: uuid.UUID) -> tuple[TestClient, SimpleNamespace]:
    app = FastAPI()
    app.include_router(router)
    user = SimpleNamespace(id=user_id, is_superuser=False)
    app.dependency_overrides[get_repository_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), user


def test_read_repositories_passes_user_object() -> None:
    """Pass the authenticated user intact to list orchestration."""
    service = FakeRepositoryService()
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)

    read_repositories(service, user, skip=10, limit=20)

    assert service.list_calls == [{"user": user, "skip": 10, "limit": 20}]


def test_read_repository_passes_user_object() -> None:
    """Pass the authenticated user intact to get orchestration."""
    service = FakeRepositoryService()
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository_id = uuid.uuid4()

    read_repository(service, user, repository_id)

    assert service.get_calls == [{"repository_id": repository_id, "user": user}]


def test_create_repository_passes_request_and_user_objects() -> None:
    """Pass validated create input and user intact to the service."""
    service = FakeRepositoryService()
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository = GitRepositoryCreate(repository_url="https://github.com/openai/openai-python.git", token="secret-token", token_expiration_days=30)
    background_tasks = BackgroundTasks()
    resources = object()

    create_repository(service=service, current_user=user, weaviate_resources=resources, background_tasks=background_tasks, repository_in=repository)

    assert service.create_calls == [{"repository": repository, "user": user, "background_tasks": background_tasks, "weaviate_resources": resources}]


def test_update_repository_returns_empty_204() -> None:
    """Expose the credential update as an empty successful response."""
    service = FakeRepositoryService()
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    client, user = _client(service, user_id)
    with client:
        response = client.put(f"/repositories/{repository_id}", json={"token": "replacement-token", "token_expiration_days": None})

    assert response.status_code == 204
    assert response.content == b""
    assert len(service.update_calls) == 1
    call = service.update_calls[0]
    assert call["repository_id"] == repository_id
    assert call["repository"].token == "replacement-token"
    assert call["repository"].token_expiration_days is None
    assert call["user"] is user


def test_delete_repository_returns_empty_204() -> None:
    """Expose coordinated deletion as an empty successful response."""
    service = FakeRepositoryService()
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    client, user = _client(service, user_id)
    with client:
        response = client.delete(f"/repositories/{repository_id}")

    assert response.status_code == 204
    assert service.delete_calls == [{"repository_id": repository_id, "user": user}]
