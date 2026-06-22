"""Test Repository Session lifecycle rules."""

import uuid

import pytest

from app.core.errors.repository_errors import RepositoryAccessForbidden, RepositoryNotFound
from app.core.errors.session_errors import RepositoryNotReady, RepositorySessionAccessForbidden
from app.db.models import Repository, RepositorySession, User
from app.enums import RepositoryStatus
from app.schemas import RepositorySessionCreate
from app.services import RepositorySessionService


class FakeRepositoryStore:
    def __init__(self, repository: Repository | None) -> None:
        self.repository = repository

    def get_by_id(self, repository_id: uuid.UUID) -> Repository | None:
        if self.repository and self.repository.id == repository_id:
            return self.repository
        return None


class FakeRepositorySessionStore:
    def __init__(self, repository_session: RepositorySession | None = None, *, page: list[RepositorySession] | None = None, total: int = 0) -> None:
        self.repository_session = repository_session
        self.saved = []
        self.append_calls = []
        self.page = page or []
        self.total = total
        self.page_calls = []
        self.count_calls = []

    def get_page(self, *, skip, limit, user_id=None, repository_id=None):
        self.page_calls.append({"skip": skip, "limit": limit, "user_id": user_id, "repository_id": repository_id})
        return self.page

    def count(self, *, user_id=None, repository_id=None):
        self.count_calls.append({"user_id": user_id, "repository_id": repository_id})
        return self.total

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


def _repository(user_id: uuid.UUID, *, status: RepositoryStatus = RepositoryStatus.ready) -> Repository:
    return Repository(user_id=user_id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai", status=status)


def test_unfiltered_list_scopes_to_owner_and_wraps_data_with_total_count() -> None:
    user_id = uuid.uuid4()
    sessions = [RepositorySession(user_id=user_id, repository_id=uuid.uuid4())]
    session_store = FakeRepositorySessionStore(page=sessions, total=5)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))

    result = service.list_sessions(user=_user(user_id), repository_id=None, skip=10, limit=20)

    assert [session.id for session in result.data] == [sessions[0].id]
    assert result.count == 5
    assert session_store.page_calls == [{"skip": 10, "limit": 20, "user_id": user_id, "repository_id": None}]
    assert session_store.count_calls == [{"user_id": user_id, "repository_id": None}]


def test_superuser_list_bypasses_owner_scoping() -> None:
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))
    superuser = User(id=uuid.uuid4(), email="root@example.com", hashed_password="not-used", is_superuser=True)

    service.list_sessions(user=superuser, repository_id=None, skip=0, limit=100)

    assert session_store.page_calls[0]["user_id"] is None
    assert session_store.count_calls[0]["user_id"] is None


def test_filtered_list_validates_then_passes_repository_id_to_the_store() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id)
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    service.list_sessions(user=_user(user_id), repository_id=repository.id, skip=0, limit=100)

    assert session_store.page_calls[0]["repository_id"] == repository.id
    assert session_store.count_calls[0]["repository_id"] == repository.id


def test_filtered_list_returns_404_when_repository_is_missing() -> None:
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))

    with pytest.raises(RepositoryNotFound):
        service.list_sessions(user=_user(uuid.uuid4()), repository_id=uuid.uuid4(), skip=0, limit=100)

    assert session_store.page_calls == []


def test_filtered_list_returns_403_when_caller_does_not_own_the_repository() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    with pytest.raises(RepositoryAccessForbidden):
        service.list_sessions(user=_user(uuid.uuid4()), repository_id=repository.id, skip=0, limit=100)

    assert session_store.page_calls == []


def test_superuser_filtered_list_bypasses_repository_ownership() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))
    superuser = User(id=uuid.uuid4(), email="root@example.com", hashed_password="not-used", is_superuser=True)

    service.list_sessions(user=superuser, repository_id=repository.id, skip=0, limit=100)

    assert session_store.page_calls[0]["repository_id"] == repository.id


def test_filtered_list_does_not_enforce_repository_readiness() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id, status=RepositoryStatus.indexing)
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    result = service.list_sessions(user=_user(user_id), repository_id=repository.id, skip=0, limit=100)

    assert result.count == 0
    assert session_store.page_calls[0]["repository_id"] == repository.id


def test_user_cannot_create_session_for_another_users_repository() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    with pytest.raises(RepositoryAccessForbidden):
        service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id), user=_user(uuid.uuid4()))

    assert session_store.saved == []


def test_user_cannot_create_session_until_repository_is_ready() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id, status=RepositoryStatus.indexing)
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    with pytest.raises(RepositoryNotReady):
        service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id), user=_user(user_id))

    assert session_store.saved == []


def test_create_session_uses_blank_placeholder_title() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id)
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository))

    created = service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id, title="Client supplied title"), user=_user(user_id))

    assert created.title == "New session"
    assert session_store.saved[0].title == "New session"


def test_user_cannot_read_another_users_session_history() -> None:
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    service = RepositorySessionService(FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None))

    with pytest.raises(RepositorySessionAccessForbidden):
        service.get_recent_history(repository_session_id=repository_session.id, user=_user(uuid.uuid4()))


def test_owned_exchange_is_persisted_through_one_store_operation() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    session_store = FakeRepositorySessionStore(repository_session)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None))
    user = _user(user_id)

    service.record_exchange(repository_session_id=repository_session.id, user=user, user_message="question", assistant_message="answer")

    assert session_store.append_calls == [(repository_session.id, {"user_message": "question", "assistant_message": "answer"})]
