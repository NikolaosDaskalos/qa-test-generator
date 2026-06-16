"""Test the unified-graph session orchestration in the session service."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.enums.coding_run import CodingRunStatus
from app.models.coding_run import CodingRun
from app.models.repository import Repository
from app.models.session import RepositorySession, SessionHistory
from app.models.user import User
from app.schemas.agent_stream import Citation, PatchResult, Result, ReviewResult, RunFailure, Stage, Token
from app.schemas.generation import ExternalReference, GeneratedFile
from app.schemas.review import ReviewFinding
from app.services.session_service import RepositorySessionService


class FakeRepositoryStore:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def get_by_id(self, repository_id):
        return self.repository if self.repository.id == repository_id else None


class FakeSessionStore:
    def __init__(self, repository_session: RepositorySession) -> None:
        self.repository_session = repository_session
        self.appended = []

    def get_by_id(self, repository_session_id):
        return self.repository_session if self.repository_session.id == repository_session_id else None

    def get_recent_history(self, repository_session_id):
        return []

    def append_exchange(self, repository_session_id, *, user_message, assistant_message, assistant_citations=None):
        self.appended.append((repository_session_id, user_message, assistant_message, assistant_citations))
        assistant = SessionHistory(id=uuid.uuid4(), session_id=repository_session_id, role="assistant", content=assistant_message, position=2)
        return SimpleNamespace(), assistant


class FakeGraph:
    def __init__(self, stream_items, final_values) -> None:
        self._items = stream_items
        self._final = final_values
        self.streamed = []

    def stream(self, graph_input, config, stream_mode):
        self.streamed.append((graph_input, config, stream_mode))
        yield from self._items

    def get_state(self, config):
        return SimpleNamespace(values=self._final)


def _user():
    return User(id=uuid.uuid4(), email="o@example.com", hashed_password="x")


def _wiring(user, *, indexed_commit_sha=None):
    repository = Repository(
        id=uuid.uuid4(), user_id=user.id, name="r", repository_url="https://github.com/o/r.git", owner="o", local_path="/checkout", indexed_commit_sha=indexed_commit_sha
    )
    repository_session = RepositorySession(id=uuid.uuid4(), owner_id=user.id, repository_id=repository.id)
    session_store = FakeSessionStore(repository_session)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))
    return service, session_store, repository_session


class _Msg:
    def __init__(self, content):
        self.content = content


def test_stream_session_passes_through_events_and_persists_repository_answer():
    user = _user()
    service, session_store, repository_session = _wiring(user)
    items = [
        ("custom", Stage(stage="classifying")),
        ("custom", Stage(stage="retrieving")),
        ("custom", Stage(stage="generating")),
        ("messages", (_Msg("hello"), {"langgraph_node": "generate"})),
    ]
    final = {"intent": "repository_question", "answer": "hello", "citations": [Citation(source="app/a.py")]}
    graph = FakeGraph(items, final)

    events = list(service.stream_session(repository_session_id=repository_session.id, user=user, question="q", graph=graph, thread_id="t-1"))

    assert Stage(stage="classifying") in events
    assert Token(content="hello") in events
    terminal = events[-1]
    assert isinstance(terminal, Result)
    assert terminal.answer == "hello"
    assert terminal.citations == [Citation(source="app/a.py")]
    # The graph was driven under the session's identity and per-run thread id.
    graph_input, config, _modes = graph.streamed[0]
    assert graph_input["repository_session_id"] == repository_session.id
    assert graph_input["repository_id"] == repository_session.repository_id
    assert graph_input["checkout_root"] == "/checkout"
    assert config["configurable"]["thread_id"] == "t-1"
    assert session_store.appended[0][2] == "hello"


def test_stream_session_emits_run_failure_terminal_for_rejected_task():
    user = _user()
    service, session_store, repository_session = _wiring(user)
    run_id = uuid.uuid4()
    items = [("custom", Stage(stage="classifying")), ("custom", Stage(stage="planning"))]
    final = {"intent": "test_generation", "failure": RunFailure(coding_run_id=run_id, failed_stage="planning", reason="Out of scope")}
    graph = FakeGraph(items, final)

    events = list(service.stream_session(repository_session_id=repository_session.id, user=user, question="refactor", graph=graph, thread_id="t-2"))

    terminal = events[-1]
    assert isinstance(terminal, RunFailure)
    assert terminal.failed_stage == "planning"
    assert terminal.coding_run_id == run_id
    # A rejected task never persists a session exchange.
    assert session_store.appended == []


def test_stream_session_emits_patch_result_terminal_for_a_generated_patch():
    user = _user()
    service, session_store, repository_session = _wiring(user)
    run_id = uuid.uuid4()
    patch = PatchResult(
        coding_run_id=run_id,
        diff="diff --git a/tests/test_x.py b/tests/test_x.py",
        generated_files=[GeneratedFile(path="tests/test_x.py", content="def test_x(): ...")],
        external_references=[ExternalReference(url="https://docs.pytest.org", title="pytest")],
    )
    items = [("custom", Stage(stage="generating"))]
    final = {"intent": "test_generation", "patch_result": patch}
    graph = FakeGraph(items, final)

    events = list(service.stream_session(repository_session_id=repository_session.id, user=user, question="add tests", graph=graph, thread_id="t-3"))

    terminal = events[-1]
    assert isinstance(terminal, PatchResult)
    assert terminal.coding_run_id == run_id
    assert [file.path for file in terminal.generated_files] == ["tests/test_x.py"]
    # A generated patch is reported, not persisted as a session answer exchange.
    assert session_store.appended == []


def test_stream_session_emits_review_result_terminal_for_a_reviewed_patch():
    user = _user()
    service, session_store, repository_session = _wiring(user)
    run_id = uuid.uuid4()
    review = ReviewResult(
        coding_run_id=run_id,
        accepted=True,
        findings=[ReviewFinding(category="coverage", detail="covers happy and unhappy paths")],
        diff="diff --git a/tests/test_x.py b/tests/test_x.py",
    )
    items = [("custom", Stage(stage="reviewing"))]
    final = {"intent": "test_generation", "review_result": review}
    graph = FakeGraph(items, final)

    events = list(service.stream_session(repository_session_id=repository_session.id, user=user, question="add tests", graph=graph, thread_id="t-rev"))

    terminal = events[-1]
    assert isinstance(terminal, ReviewResult)
    assert terminal.coding_run_id == run_id
    assert terminal.accepted is True
    assert "not executed" in terminal.disclaimer.lower()
    # A reviewed patch is reported, not persisted as a session answer exchange.
    assert session_store.appended == []


def test_stream_session_passes_the_indexed_commit_to_the_graph():
    user = _user()
    service, _store, repository_session = _wiring(user, indexed_commit_sha="a" * 40)
    graph = FakeGraph([], {"intent": "test_generation"})

    list(service.stream_session(repository_session_id=repository_session.id, user=user, question="add tests", graph=graph, thread_id="t-4"))

    graph_input, _config, _modes = graph.streamed[0]
    assert graph_input["indexed_commit_sha"] == "a" * 40


def test_stream_session_rejects_a_session_owned_by_another_user():
    user = _user()
    service, _store, repository_session = _wiring(user)
    other = _user()

    with pytest.raises(HTTPException) as exc:
        list(service.stream_session(repository_session_id=repository_session.id, user=other, question="q", graph=FakeGraph([], {}), thread_id="t"))

    assert exc.value.status_code == 403


class FakeCodingRunStore:
    def __init__(self, run) -> None:
        self.run = run

    def get_by_id(self, coding_run_id):
        return self.run if self.run is not None and self.run.repository_session_id is not None else None


def test_get_owned_run_returns_a_run_owned_through_the_session():
    user = _user()
    service, _store, repository_session = _wiring(user)
    run = CodingRun(repository_session_id=repository_session.id, thread_id="t-own", status=CodingRunStatus.awaiting_approval)
    service.coding_run_store = FakeCodingRunStore(run)

    found = service.get_owned_run(repository_session_id=repository_session.id, coding_run_id=run.id, user=user)

    assert found is run


def test_get_owned_run_rejects_a_run_belonging_to_another_session():
    user = _user()
    service, _store, repository_session = _wiring(user)
    foreign_run = CodingRun(repository_session_id=uuid.uuid4(), thread_id="t-foreign", status=CodingRunStatus.awaiting_approval)
    service.coding_run_store = FakeCodingRunStore(foreign_run)

    with pytest.raises(HTTPException) as exc:
        service.get_owned_run(repository_session_id=repository_session.id, coding_run_id=foreign_run.id, user=user)

    assert exc.value.status_code == 404


def test_get_owned_run_rejects_a_session_owned_by_another_user():
    user = _user()
    service, _store, repository_session = _wiring(user)
    run = CodingRun(repository_session_id=repository_session.id, thread_id="t-x", status=CodingRunStatus.awaiting_approval)
    service.coding_run_store = FakeCodingRunStore(run)
    other = _user()

    with pytest.raises(HTTPException) as exc:
        service.get_owned_run(repository_session_id=repository_session.id, coding_run_id=run.id, user=other)

    assert exc.value.status_code == 403
