"""Test the AI Cost rollup route contracts (ADR-0014)."""

import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_cost_rollup_service, get_current_user
from app.api.exception_handlers import register_exception_handlers
from app.api.routes.costs import router
from app.core.errors.session_errors import RepositorySessionAccessForbidden, RepositorySessionNotFound
from app.schemas import AiCostRollupPublic


class FakeCostRollupService:
    def __init__(self, rollup: AiCostRollupPublic | None = None, *, raises: Exception | None = None) -> None:
        self.rollup = rollup or AiCostRollupPublic(cost=0.03, input_tokens=400, output_tokens=70, total_tokens=470)
        self.raises = raises
        self.calls = []

    def session_rollup(self, **kwargs):
        self.calls.append(("session", kwargs))
        if self.raises is not None:
            raise self.raises
        return self.rollup

    def repository_rollup(self, **kwargs):
        self.calls.append(("repository", kwargs))
        if self.raises is not None:
            raise self.raises
        return self.rollup

    def user_rollup(self, **kwargs):
        self.calls.append(("user", kwargs))
        return self.rollup

    def all_users_rollup(self, **kwargs):
        self.calls.append(("all", kwargs))
        return self.rollup


def _app(service, *, user):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_cost_rollup_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_owner_can_read_a_session_rollup() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    service = FakeCostRollupService()

    with TestClient(_app(service, user=user)) as client:
        response = client.get(f"/costs/session/{session_id}")

    assert response.status_code == 200
    assert response.json() == {"cost": 0.03, "input_tokens": 400, "output_tokens": 70, "total_tokens": 470}
    kind, kwargs = service.calls[0]
    assert kind == "session"
    assert kwargs["repository_session_id"] == session_id
    assert kwargs["user"] is user


def test_owner_can_read_a_repository_rollup() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository_id = uuid.uuid4()
    service = FakeCostRollupService()

    with TestClient(_app(service, user=user)) as client:
        response = client.get(f"/costs/repository/{repository_id}")

    assert response.status_code == 200
    kind, kwargs = service.calls[0]
    assert kind == "repository"
    assert kwargs["repository_id"] == repository_id
    assert kwargs["user"] is user


def test_user_can_read_their_own_rollup() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeCostRollupService()

    with TestClient(_app(service, user=user)) as client:
        response = client.get("/costs/me")

    assert response.status_code == 200
    kind, kwargs = service.calls[0]
    assert kind == "user"
    assert kwargs["user"] is user


def test_a_session_rollup_not_owned_maps_to_the_shared_owner_scoped_error() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeCostRollupService(raises=RepositorySessionNotFound())

    with TestClient(_app(service, user=user)) as client:
        response = client.get(f"/costs/session/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Repository Session not found"}


def test_a_session_rollup_for_another_owner_is_forbidden() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeCostRollupService(raises=RepositorySessionAccessForbidden())

    with TestClient(_app(service, user=user)) as client:
        response = client.get(f"/costs/session/{uuid.uuid4()}")

    assert response.status_code == 403


def test_all_users_rollup_is_served_to_a_superuser() -> None:
    superuser = SimpleNamespace(id=uuid.uuid4(), is_superuser=True)
    service = FakeCostRollupService()

    with TestClient(_app(service, user=superuser)) as client:
        response = client.get("/costs/all")

    assert response.status_code == 200
    assert service.calls[0][0] == "all"


def test_all_users_rollup_is_refused_to_a_non_superuser() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeCostRollupService()

    with TestClient(_app(service, user=user)) as client:
        response = client.get("/costs/all")

    assert response.status_code == 403
    assert service.calls == []


def test_rollup_requires_authentication() -> None:
    service = FakeCostRollupService()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_cost_rollup_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/costs/me")

    assert response.status_code == 401
    assert service.calls == []
