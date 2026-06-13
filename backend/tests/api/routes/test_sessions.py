"""Test Repository Session route contracts."""

import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.sessions import router
from app.dependencies import get_current_user, get_repository_session_service
from app.enums.session import SessionMessageRole
from app.models.session import RepositorySession, SessionHistory


class FakeRepositorySessionService:
    def __init__(self, repository_session: RepositorySession, history: list[SessionHistory] | None = None) -> None:
        self.repository_session = repository_session
        self.history = history or []
        self.create_calls = []
        self.history_calls = []

    def create_session(self, **kwargs) -> RepositorySession:
        self.create_calls.append(kwargs)
        return self.repository_session

    def get_recent_history(self, **kwargs) -> list[SessionHistory]:
        self.history_calls.append(kwargs)
        return self.history


def test_owner_can_create_repository_session_for_ready_repository() -> None:
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    repository_session = RepositorySession(owner_id=user_id, repository_id=repository_id, title="Authentication tests")
    service = FakeRepositorySessionService(repository_session)
    user = SimpleNamespace(id=user_id, is_superuser=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.post("/sessions", json={"repository_id": str(repository_id), "title": "Authentication tests"})

    assert response.status_code == 201
    assert response.json()["repository_id"] == str(repository_id)
    assert response.json()["title"] == "Authentication tests"
    assert service.create_calls[0]["user"] is user
    assert service.create_calls[0]["session_in"].repository_id == repository_id


def test_create_repository_session_requires_authentication() -> None:
    repository_session = RepositorySession(owner_id=uuid.uuid4(), repository_id=uuid.uuid4())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: (FakeRepositorySessionService(repository_session))

    with TestClient(app) as client:
        response = client.post("/sessions", json={"repository_id": str(repository_session.repository_id)})

    assert response.status_code == 401


def test_owner_can_read_session_history() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(owner_id=user_id, repository_id=uuid.uuid4())
    history = [
        SessionHistory(session_id=repository_session.id, role=SessionMessageRole.user, content="How is authentication tested?", position=1),
        SessionHistory(session_id=repository_session.id, role=SessionMessageRole.assistant, content="The repository uses route tests.", position=2),
    ]
    service = FakeRepositorySessionService(repository_session, history)
    user = SimpleNamespace(id=user_id, is_superuser=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.get(f"/sessions/{repository_session.id}/history")

    assert response.status_code == 200
    assert [message["role"] for message in response.json()["data"]] == ["user", "assistant"]
    assert service.history_calls == [{"repository_session_id": repository_session.id, "user": user}]
