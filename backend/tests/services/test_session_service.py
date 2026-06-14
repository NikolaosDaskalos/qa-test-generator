"""Test Repository Session lifecycle rules."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.enums.repository import RepositoryStatus
from app.enums.session import SessionMessageRole
from app.models.repository import Repository
from app.models.session import RepositorySession, SessionHistory
from app.models.user import User
from app.schemas.session import RepositorySessionCreate
from app.services.session_service import RepositorySessionService


class FakeRepositoryStore:
    def __init__(self, repository: Repository | None) -> None:
        self.repository = repository

    def get_by_id(self, repository_id: uuid.UUID) -> Repository | None:
        if self.repository and self.repository.id == repository_id:
            return self.repository
        return None


class FakeRepositorySessionStore:
    def __init__(self, repository_session: RepositorySession | None = None) -> None:
        self.repository_session = repository_session
        self.saved = []
        self.append_calls = []

    def save(self, repository_session):
        self.repository_session = repository_session
        self.saved.append(repository_session)
        return repository_session

    def get_by_id(self, repository_session_id):
        if self.repository_session and self.repository_session.id == repository_session_id:
            return self.repository_session
        return None

    def get_recent_history(self, repository_session_id):
        raise AssertionError("history must not be loaded before ownership is checked")

    def append_exchange(self, repository_session_id, **kwargs):
        self.append_calls.append((repository_session_id, kwargs))
        return ()


def _user(user_id: uuid.UUID) -> User:
    return User(id=user_id, email=f"{user_id}@example.com", hashed_password="not-used")


def _repository(owner_id: uuid.UUID, *, status: RepositoryStatus = RepositoryStatus.ready) -> Repository:
    return Repository(user_id=owner_id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai", status=status)


def test_user_cannot_create_session_for_another_users_repository() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    with pytest.raises(HTTPException) as exc_info:
        service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id), user=_user(uuid.uuid4()))

    assert exc_info.value.status_code == 403
    assert session_store.saved == []


def test_user_cannot_create_session_until_repository_is_ready() -> None:
    owner_id = uuid.uuid4()
    repository = _repository(owner_id, status=RepositoryStatus.indexing)
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    with pytest.raises(HTTPException) as exc_info:
        service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id), user=_user(owner_id))

    assert exc_info.value.status_code == 409
    assert session_store.saved == []


def test_user_cannot_read_another_users_session_history() -> None:
    repository_session = RepositorySession(owner_id=uuid.uuid4(), repository_id=uuid.uuid4())
    service = RepositorySessionService(FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None))

    with pytest.raises(HTTPException) as exc_info:
        service.get_recent_history(repository_session_id=repository_session.id, user=_user(uuid.uuid4()))

    assert exc_info.value.status_code == 403


def test_owned_exchange_is_persisted_through_one_store_operation() -> None:
    owner_id = uuid.uuid4()
    repository_session = RepositorySession(owner_id=owner_id, repository_id=uuid.uuid4())
    session_store = FakeRepositorySessionStore(repository_session)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))
    user = _user(owner_id)

    service.record_exchange(repository_session_id=repository_session.id, user=user, user_message="question", assistant_message="answer")

    assert session_store.append_calls == [(repository_session.id, {"user_message": "question", "assistant_message": "answer"})]


class FakeAnsweringSessionStore:
    """Session store fake that exposes history and records persistence."""

    def __init__(self, repository_session: RepositorySession, history: list[SessionHistory] | None = None) -> None:
        self.repository_session = repository_session
        self.history = history or []
        self.append_calls = []
        self.user_message = SimpleNamespace(id=uuid.uuid4())
        self.assistant_message = SimpleNamespace(id=uuid.uuid4())

    def get_by_id(self, repository_session_id):
        if self.repository_session.id == repository_session_id:
            return self.repository_session
        return None

    def get_recent_history(self, repository_session_id):
        return self.history

    def append_exchange(self, repository_session_id, **kwargs):
        self.append_calls.append((repository_session_id, kwargs))
        return self.user_message, self.assistant_message


class FakePipeline:
    """Records the answer request and replays canned Agent Stream events."""

    def __init__(self, events) -> None:
        self.events = events
        self.calls = []

    def answer_stream(self, question, **kwargs):
        self.calls.append((question, kwargs))
        yield from self.events


def test_answer_question_binds_streams_and_persists_with_citations() -> None:
    owner_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    repository_session = RepositorySession(owner_id=owner_id, repository_id=repository_id)
    history = [
        SessionHistory(session_id=repository_session.id, role=SessionMessageRole.user, content="Earlier question", position=1),
        SessionHistory(session_id=repository_session.id, role=SessionMessageRole.assistant, content="Earlier answer", position=2),
    ]
    session_store = FakeAnsweringSessionStore(repository_session, history)
    pipeline = FakePipeline(
        [
            {"type": "token", "content": "Auth "},
            {"type": "token", "content": "is route-tested."},
            {
                "type": "done",
                "sources": [
                    {"source": "app/auth.py", "page": "", "chunk": "c1", "score": None},
                    {"source": "app/auth.py", "page": "", "chunk": "c2", "score": None},
                    {"source": "app/login.py", "page": "", "chunk": "c3", "score": None},
                ],
            },
        ]
    )
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))

    events = list(
        service.answer_question(repository_session_id=repository_session.id, user=_user(owner_id), question="How is auth tested?", pipeline=pipeline)
    )

    # Retrieval is bound to the session's immutable Repository and forwards bounded history.
    assert pipeline.calls == [
        (
            "How is auth tested?",
            {
                "repository_id": repository_id,
                "history": [
                    {"role": "user", "content": "Earlier question"},
                    {"role": "assistant", "content": "Earlier answer"},
                ],
            },
        )
    ]

    # Ordered Agent Stream: stage progress, answer tokens, citations, one terminal result.
    assert [event["type"] for event in events] == ["stage", "stage", "token", "token", "citations", "result"]
    assert [event["stage"] for event in events if event["type"] == "stage"] == ["retrieving", "generating"]
    citations_event = next(event for event in events if event["type"] == "citations")
    assert citations_event["citations"] == [{"source": "app/auth.py"}, {"source": "app/login.py"}]

    terminal = events[-1]
    assert terminal["repository_session_id"] == repository_session.id
    assert terminal["assistant_message_id"] == session_store.assistant_message.id
    assert terminal["answer"] == "Auth is route-tested."
    assert terminal["citations"] == [{"source": "app/auth.py"}, {"source": "app/login.py"}]

    # The exchange is persisted with the question and the answer plus a traceable citation footer.
    assert len(session_store.append_calls) == 1
    persisted_session_id, persisted = session_store.append_calls[0]
    assert persisted_session_id == repository_session.id
    assert persisted["user_message"] == "How is auth tested?"
    assert persisted["assistant_message"].startswith("Auth is route-tested.")
    assert "app/auth.py" in persisted["assistant_message"]
    assert "app/login.py" in persisted["assistant_message"]


def test_answer_question_rejects_non_owner_before_streaming() -> None:
    repository_session = RepositorySession(owner_id=uuid.uuid4(), repository_id=uuid.uuid4())
    session_store = FakeAnsweringSessionStore(repository_session)
    pipeline = FakePipeline([])
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))

    with pytest.raises(HTTPException) as exc_info:
        service.answer_question(repository_session_id=repository_session.id, user=_user(uuid.uuid4()), question="q", pipeline=pipeline)

    assert exc_info.value.status_code == 403
    assert pipeline.calls == []
    assert session_store.append_calls == []


def test_answer_question_persists_insufficient_evidence_with_empty_citations() -> None:
    owner_id = uuid.uuid4()
    repository_session = RepositorySession(owner_id=owner_id, repository_id=uuid.uuid4())
    session_store = FakeAnsweringSessionStore(repository_session)
    pipeline = FakePipeline(
        [
            {"type": "token", "content": "I don't have enough Repository Evidence."},
            {"type": "done", "sources": []},
        ]
    )
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))

    events = list(
        service.answer_question(repository_session_id=repository_session.id, user=_user(owner_id), question="unknown?", pipeline=pipeline)
    )

    terminal = events[-1]
    assert terminal["type"] == "result"
    assert terminal["citations"] == []
    assert next(event for event in events if event["type"] == "citations")["citations"] == []
    # The exchange is still persisted, and the assistant message carries no citation footer.
    persisted = session_store.append_calls[0][1]
    assert persisted["assistant_message"] == "I don't have enough Repository Evidence."
