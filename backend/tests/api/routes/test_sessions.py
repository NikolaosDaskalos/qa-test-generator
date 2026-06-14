"""Test Repository Session route contracts."""

import json
import uuid
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api.routes.sessions import router
from app.dependencies import get_current_user, get_rag_pipeline, get_repository_session_service
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


class FakeAnsweringService:
    def __init__(self, events, raises: HTTPException | None = None) -> None:
        self.events = events
        self.raises = raises
        self.answer_calls = []

    def answer_question(self, **kwargs):
        self.answer_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return iter(self.events)


def _parse_sse(body: str) -> list[dict]:
    return [json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")]


def _question_app(service, *, user=None, pipeline=object()):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_rag_pipeline] = lambda: pipeline
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_question_streams_grounded_answer_as_event_stream() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    assistant_message_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, is_superuser=False)
    events = [
        {"type": "stage", "stage": "retrieving"},
        {"type": "stage", "stage": "generating"},
        {"type": "token", "content": "Auth is route-tested."},
        {"type": "citations", "citations": [{"source": "app/auth.py"}]},
        {
            "type": "result",
            "repository_session_id": str(session_id),
            "assistant_message_id": str(assistant_message_id),
            "answer": "Auth is route-tested.",
            "citations": [{"source": "app/auth.py"}],
        },
    ]
    pipeline = object()
    service = FakeAnsweringService(events)
    app = _question_app(service, user=user, pipeline=pipeline)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{session_id}/questions", json={"question": "How is auth tested?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    streamed = _parse_sse(response.text)
    assert [event["type"] for event in streamed] == ["stage", "stage", "token", "citations", "result", "done"]
    assert streamed[3]["citations"] == [{"source": "app/auth.py"}]
    terminal = streamed[-2]
    assert terminal["assistant_message_id"] == str(assistant_message_id)
    assert terminal["answer"] == "Auth is route-tested."
    # The route binds the request to the owned session and forwards the pipeline.
    call = service.answer_calls[0]
    assert call["repository_session_id"] == session_id
    assert call["user"] is user
    assert call["question"] == "How is auth tested?"
    assert call["pipeline"] is pipeline


def test_question_streams_insufficient_evidence_with_empty_citations() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    events = [
        {"type": "stage", "stage": "retrieving"},
        {"type": "token", "content": "I don't have enough Repository Evidence."},
        {"type": "citations", "citations": []},
        {"type": "result", "repository_session_id": str(uuid.uuid4()), "assistant_message_id": str(uuid.uuid4()), "answer": "I don't have enough Repository Evidence.", "citations": []},
    ]
    service = FakeAnsweringService(events)
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "unknown?"})

    streamed = _parse_sse(response.text)
    assert next(event for event in streamed if event["type"] == "citations")["citations"] == []
    assert "enough Repository Evidence" in next(event for event in streamed if event["type"] == "token")["content"]


def test_question_surfaces_midstream_failure_as_error_then_done() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)

    class ExplodingService:
        answer_calls: list = []

        def answer_question(self, **kwargs):
            def stream():
                yield {"type": "stage", "stage": "retrieving"}
                raise RuntimeError("pipeline blew up")

            return stream()

    app = _question_app(ExplodingService(), user=user)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "boom?"})

    streamed = _parse_sse(response.text)
    assert [event["type"] for event in streamed] == ["stage", "error", "done"]
    assert "error occurred" in streamed[1]["message"].lower()


def test_question_requires_authentication() -> None:
    service = FakeAnsweringService([])
    app = _question_app(service)  # no current user override

    with TestClient(app) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "q"})

    assert response.status_code == 401
    assert service.answer_calls == []


def test_question_enforces_session_ownership() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeAnsweringService([], raises=HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"))
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "q"})

    assert response.status_code == 403
