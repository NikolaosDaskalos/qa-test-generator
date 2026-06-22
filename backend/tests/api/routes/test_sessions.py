"""Test Repository Session route contracts."""

import json
import uuid
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api.exception_handlers import register_exception_handlers
from app.api.routes.sessions import router
from app.core.errors.session_errors import RepositorySessionNotFound
from app.db.models import CodingRun, RepositorySession, SessionHistory
from app.dependencies import get_current_user, get_repository_session_service, get_session_graph
from app.enums import CodingRunStage, CodingRunStatus, SessionMessageRole
from app.schemas import Citation, RepositorySessionPublic, RepositorySessionsPublic, Result, RunApproved, RunRejected, Stage, Token


class FakeRepositorySessionService:
    def __init__(
        self,
        repository_session: RepositorySession,
        history: list[SessionHistory] | None = None,
        run: CodingRun | None = None,
        listing: RepositorySessionsPublic | None = None,
        list_raises: HTTPException | None = None,
        history_raises: Exception | None = None,
    ) -> None:
        self.repository_session = repository_session
        self.history = history or []
        self.run = run
        self.listing = listing
        self.list_raises = list_raises
        self.history_raises = history_raises
        self.create_calls = []
        self.history_calls = []
        self.run_calls = []
        self.list_calls = []

    def create_session(self, **kwargs) -> RepositorySession:
        self.create_calls.append(kwargs)
        return self.repository_session

    def list_sessions(self, **kwargs) -> RepositorySessionsPublic:
        self.list_calls.append(kwargs)
        if self.list_raises is not None:
            raise self.list_raises
        return self.listing

    def get_recent_history(self, **kwargs) -> list[SessionHistory]:
        self.history_calls.append(kwargs)
        if self.history_raises is not None:
            raise self.history_raises
        return self.history

    def get_owned_run(self, **kwargs) -> CodingRun:
        self.run_calls.append(kwargs)
        if self.run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding Run not found")
        return self.run


def test_owner_can_create_repository_session_for_ready_repository() -> None:
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=repository_id, title="Authentication tests")
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
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: (FakeRepositorySessionService(repository_session))

    with TestClient(app) as client:
        response = client.post("/sessions", json={"repository_id": str(repository_session.repository_id)})

    assert response.status_code == 401


def test_list_sessions_returns_data_and_count_and_forwards_filter_and_paging() -> None:
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=repository_id, title="Auth tests")
    listing = RepositorySessionsPublic(data=[RepositorySessionPublic.model_validate(repository_session)], count=1)
    service = FakeRepositorySessionService(repository_session, listing=listing)
    user = SimpleNamespace(id=user_id, is_superuser=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.get("/sessions", params={"repository_id": str(repository_id), "skip": 5, "limit": 25})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["data"][0]["repository_id"] == str(repository_id)
    assert service.list_calls == [{"user": user, "repository_id": repository_id, "skip": 5, "limit": 25}]


def test_list_sessions_defaults_to_no_filter_and_standard_paging() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    listing = RepositorySessionsPublic(data=[], count=0)
    service = FakeRepositorySessionService(repository_session, listing=listing)
    user = SimpleNamespace(id=user_id, is_superuser=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.get("/sessions")

    assert response.status_code == 200
    assert service.list_calls == [{"user": user, "repository_id": None, "skip": 0, "limit": 100}]


def test_list_sessions_requires_authentication() -> None:
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    service = FakeRepositorySessionService(repository_session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/sessions")

    assert response.status_code == 401
    assert service.list_calls == []


def test_list_sessions_surfaces_repository_validation_error_from_the_service() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository_session = RepositorySession(user_id=user.id, repository_id=uuid.uuid4())
    service = FakeRepositorySessionService(repository_session, list_raises=HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.get("/sessions", params={"repository_id": str(uuid.uuid4())})

    assert response.status_code == 404


def test_session_domain_error_is_translated_to_http_at_the_api_seam() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    repository_session = RepositorySession(user_id=user.id, repository_id=uuid.uuid4())
    service = FakeRepositorySessionService(repository_session, history_raises=RepositorySessionNotFound())
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as client:
        response = client.get(f"/sessions/{repository_session.id}/history")

    assert response.status_code == 404
    assert response.json() == {"detail": "Repository Session not found"}


def test_owner_can_read_session_history() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
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


def test_question_streams_insufficient_documents_with_empty_citations() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    events = [
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content="I don't have enough Repository Documents."),
        Result(repository_session_id=uuid.uuid4(), assistant_message_id=uuid.uuid4(), answer="I don't have enough Repository Documents.", citations=[]),
    ]
    service = FakeAnsweringService(events)
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "unknown?"})

    streamed = _parse_sse(response.text)
    assert next(event for event in streamed if event["type"] == "result")["citations"] == []
    assert "enough Repository Documents" in next(event for event in streamed if event["type"] == "token")["content"]


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


def test_decision_resumes_the_paused_run_through_the_same_stream() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    run_id = uuid.uuid4()
    events = [Stage(stage="reviewing"), RunRejected(coding_run_id=run_id, diff="diff --git a/tests/test_x.py b/tests/test_x.py", findings=[])]
    service = FakeAnsweringService(events)
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{session_id}/questions", json={"decision": {"coding_run_id": str(run_id), "approved": False}})

    assert response.status_code == 200
    streamed = _parse_sse(response.text)
    # The same stream surfaces the rejection terminal — no separate approval/rejection endpoint.
    assert [event["type"] for event in streamed] == ["stage", "run_rejected"]
    assert streamed[-1]["coding_run_id"] == str(run_id)
    # The route forwards the decision (and no question) to the service to resume the paused run.
    call = service.answer_calls[0]
    assert call["decision"].coding_run_id == run_id
    assert call["decision"].approved is False
    assert call["question"] is None


def test_approved_decision_streams_run_approved_terminal() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    session_id = uuid.uuid4()
    run_id = uuid.uuid4()
    service = FakeAnsweringService(
        [Stage(stage="reviewing"), RunApproved(coding_run_id=run_id, branch="qa-tests/abc123", diff="diff --git a/tests/test_x.py b/tests/test_x.py")]
    )
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{session_id}/questions", json={"decision": {"coding_run_id": str(run_id), "approved": True}})

    assert response.status_code == 200
    streamed = _parse_sse(response.text)
    assert [event["type"] for event in streamed] == ["stage", "run_approved"]
    assert streamed[-1]["coding_run_id"] == str(run_id)
    assert streamed[-1]["branch"] == "qa-tests/abc123"
    assert service.answer_calls[0]["decision"].approved is True


def test_decision_conflict_from_the_service_surfaces_as_409() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeAnsweringService([], raises=HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Coding Run is not awaiting a decision"))
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        response = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"decision": {"coding_run_id": str(uuid.uuid4()), "approved": False}})

    assert response.status_code == 409


def test_request_must_carry_either_a_question_or_a_decision() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)
    service = FakeAnsweringService([])
    app = _question_app(service, user=user)

    with TestClient(app) as client:
        empty = client.post(f"/sessions/{uuid.uuid4()}/questions", json={})
        both = client.post(f"/sessions/{uuid.uuid4()}/questions", json={"question": "q", "decision": {"coding_run_id": str(uuid.uuid4()), "approved": True}})

    assert empty.status_code == 422
    assert both.status_code == 422
    assert service.answer_calls == []


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
    service = FakeRepositorySessionService(RepositorySession(id=session_id, user_id=user.id, repository_id=uuid.uuid4()), run=run)
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
        failure_reason="The code generator could not produce a valid proposal.",
    )
    service = FakeRepositorySessionService(RepositorySession(id=session_id, user_id=user.id, repository_id=uuid.uuid4()), run=run)
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
    service = FakeRepositorySessionService(RepositorySession(id=session_id, user_id=user.id, repository_id=uuid.uuid4()), run=run)
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
    service = FakeRepositorySessionService(RepositorySession(id=session_id, user_id=user.id, repository_id=uuid.uuid4()), run=None)
    app = _lookup_app(service, user=user)

    with TestClient(app) as client:
        response = client.get(f"/sessions/{session_id}/runs/{uuid.uuid4()}")

    assert response.status_code == 404


def test_run_lookup_requires_authentication() -> None:
    service = FakeRepositorySessionService(RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4()))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository_session_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(f"/sessions/{uuid.uuid4()}/runs/{uuid.uuid4()}")

    assert response.status_code == 401
    assert service.run_calls == []
