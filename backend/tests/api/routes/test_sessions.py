"""Test Repository Session route contracts."""

import json
import uuid
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api.routes.sessions import router
from app.dependencies import get_current_user, get_repository_session_service, get_session_graph
from app.enums.coding_run import CodingRunStage, CodingRunStatus
from app.enums.session import SessionMessageRole
from app.models.coding_run import CodingRun
from app.models.session import RepositorySession, SessionHistory
from app.schemas.agent_stream import Citation, Result, Stage, Token


class FakeRepositorySessionService:
    def __init__(self, repository_session: RepositorySession, history: list[SessionHistory] | None = None, run: CodingRun | None = None) -> None:
        self.repository_session = repository_session
        self.history = history or []
        self.run = run
        self.create_calls = []
        self.history_calls = []
        self.run_calls = []

    def create_session(self, **kwargs) -> RepositorySession:
        self.create_calls.append(kwargs)
        return self.repository_session

    def get_recent_history(self, **kwargs) -> list[SessionHistory]:
        self.history_calls.append(kwargs)
        return self.history

    def get_owned_run(self, **kwargs) -> CodingRun:
        self.run_calls.append(kwargs)
        if self.run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding Run not found")
        return self.run


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
        SessionHistory(
            session_id=repository_session.id,
            role=SessionMessageRole.assistant,
            content="The repository uses route tests.",
            citations=[{"source": "app/auth.py"}, {"source": "app/login.py"}],
            position=2,
        ),
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
    messages = response.json()["data"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    # Citations surface structurally on the read contract instead of being parsed out of the message text.
    assert messages[0]["citations"] == []
    assert messages[1]["citations"] == [{"source": "app/auth.py"}, {"source": "app/login.py"}]
    assert service.history_calls == [{"repository_session_id": repository_session.id, "user": user}]


class FakeAnsweringService:
    def __init__(self, events, raises: HTTPException | None = None) -> None:
        self.events = events
        self.raises = raises
        self.answer_calls = []

    def stream_session(self, **kwargs):
        self.answer_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return iter(self.events)


def _parse_sse(body: str) -> list[dict]:
    return [json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")]


def _question_app(service, *, user=None, graph=object()):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_session_graph] = lambda: graph
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_question_streams_grounded_answer_as_event_stream() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    assistant_message_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, is_superuser=False)
    events = [
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content="Auth is route-tested."),
        Result(
            repository_session_id=session_id,
            assistant_message_id=assistant_message_id,
            answer="Auth is route-tested.",
            citations=[Citation(source="app/auth.py")],
        ),
    ]
    graph = object()
    service = FakeAnsweringService(events)
    app = _question_app(service, user=user, graph=graph)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{session_id}/questions", json={"question": "How is auth tested?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    streamed = _parse_sse(response.text)
    # Exactly one terminal frame: the Result, which carries the citations. The double-`done` is gone.
    assert [event["type"] for event in streamed] == ["stage", "stage", "token", "result"]
    terminal = streamed[-1]
    assert terminal["repository_session_id"] == str(session_id)
    assert terminal["assistant_message_id"] == str(assistant_message_id)
    assert terminal["answer"] == "Auth is route-tested."
    assert terminal["citations"] == [{"source": "app/auth.py"}]
    # The route binds the request to the owned session and drives the unified graph under a per-run thread id.
    call = service.answer_calls[0]
    assert call["repository_session_id"] == session_id
    assert call["user"] is user
    assert call["question"] == "How is auth tested?"
    assert call["graph"] is graph
    assert isinstance(call["thread_id"], str) and call["thread_id"]


def test_question_streams_insufficient_evidence_with_empty_citations() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    events = [
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content="I don't have enough Repository Evidence."),
        Result(repository_session_id=uuid.uuid4(), assistant_message_id=uuid.uuid4(), answer="I don't have enough Repository Evidence.", citations=[]),
    ]
    service = FakeAnsweringService(events)
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "unknown?"})

    streamed = _parse_sse(response.text)
    assert next(event for event in streamed if event["type"] == "result")["citations"] == []
    assert "enough Repository Evidence" in next(event for event in streamed if event["type"] == "token")["content"]


def test_question_surfaces_midstream_failure_as_out_of_band_error() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)

    class ExplodingService:
        answer_calls: list = []

        def stream_session(self, **kwargs):
            def stream():
                yield Stage(stage="retrieving")
                raise RuntimeError("pipeline blew up")

            return stream()

    app = _question_app(ExplodingService(), user=user)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "boom?"})

    streamed = _parse_sse(response.text)
    # A single out-of-band transport error frame closes the stream — no separate `done`.
    assert [event["type"] for event in streamed] == ["stage", "error"]
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


def _lookup_app(service, *, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_owner_can_read_coding_run_state_and_findings() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    run = CodingRun(
        repository_session_id=session_id,
        thread_id="t-1",
        status=CodingRunStatus.changes_requested,
        diff="diff --git a/tests/test_x.py b/tests/test_x.py",
        review_findings=[{"category": "coverage", "detail": "missing unhappy-path test"}],
    )
    service = FakeRepositorySessionService(RepositorySession(id=session_id, owner_id=user.id, repository_id=uuid.uuid4()), run=run)
    app = _lookup_app(service, user=user)

    with TestClient(app) as client:
        response = client.get(f"/sessions/{session_id}/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "changes_requested"
    assert body["diff"].startswith("diff --git")
    assert body["review_findings"] == [{"category": "coverage", "detail": "missing unhappy-path test"}]
    # User-visible output states tests were not executed and runtime correctness was not verified.
    assert "not executed" in body["disclaimer"].lower()
    call = service.run_calls[0]
    assert call["repository_session_id"] == session_id
    assert call["coding_run_id"] == run.id
    assert call["user"] is user


def test_run_lookup_exposes_failure_information() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    run = CodingRun(
        repository_session_id=session_id,
        thread_id="t-2",
        status=CodingRunStatus.failed,
        failed_stage=CodingRunStage.generating,
        failure_reason="The test generator could not produce a valid proposal.",
    )
    service = FakeRepositorySessionService(RepositorySession(id=session_id, owner_id=user.id, repository_id=uuid.uuid4()), run=run)
    app = _lookup_app(service, user=user)

    with TestClient(app) as client:
        response = client.get(f"/sessions/{session_id}/runs/{run.id}")

    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_stage"] == "generating"
    assert "valid proposal" in body["failure_reason"]


def test_owner_can_read_coding_run_patch_content() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    run = CodingRun(
        repository_session_id=session_id,
        thread_id="t-3",
        status=CodingRunStatus.awaiting_approval,
        diff="diff --git a/tests/test_x.py b/tests/test_x.py",
        generated_files=[{"path": "tests/test_x.py", "content": "def test_x(): ..."}],
        external_references=[{"url": "https://docs.pytest.org", "title": "pytest"}],
    )
    service = FakeRepositorySessionService(RepositorySession(id=session_id, owner_id=user.id, repository_id=uuid.uuid4()), run=run)
    app = _lookup_app(service, user=user)

    with TestClient(app) as client:
        response = client.get(f"/sessions/{session_id}/runs/{run.id}/patch")

    assert response.status_code == 200
    body = response.json()
    assert body["diff"].startswith("diff --git")
    assert body["generated_files"] == [{"path": "tests/test_x.py", "content": "def test_x(): ..."}]
    assert body["external_references"] == [{"url": "https://docs.pytest.org", "title": "pytest"}]


def test_run_lookup_returns_404_for_a_run_not_owned_through_the_session() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    service = FakeRepositorySessionService(RepositorySession(id=session_id, owner_id=user.id, repository_id=uuid.uuid4()), run=None)
    app = _lookup_app(service, user=user)

    with TestClient(app) as client:
        response = client.get(f"/sessions/{session_id}/runs/{uuid.uuid4()}")

    assert response.status_code == 404


def test_run_lookup_requires_authentication() -> None:
    service = FakeRepositorySessionService(RepositorySession(owner_id=uuid.uuid4(), repository_id=uuid.uuid4()))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(f"/sessions/{uuid.uuid4()}/runs/{uuid.uuid4()}")

    assert response.status_code == 401
    assert service.run_calls == []
