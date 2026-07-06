"""Test Repository Session lifecycle rules."""

import uuid

import pytest

from app.core.errors.repository_errors import RepositoryAccessForbidden, RepositoryNotFound
from app.core.errors.session_errors import RepositoryNotReady, RepositorySessionAccessForbidden, RepositorySessionNotFound
from app.db.models import Repository, RepositorySession, UsageRecord, User
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


class FakeCodingRunStore:
    def __init__(self, run=None) -> None:
        self.run = run
        self.lookups = []

    def get_by_id(self, coding_run_id):
        self.lookups.append(coding_run_id)
        return self.run


class FakeUsageRecordStore:
    def __init__(self, records=None) -> None:
        self.created = []
        self.records = records or []
        self.list_calls = []

    def create(self, **kwargs):
        self.created.append(kwargs)

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.records


class FakeRepositorySessionStore:
    def __init__(self, repository_session: RepositorySession | None = None, *, page: list[RepositorySession] | None = None, total: int = 0) -> None:
        self.repository_session = repository_session
        self.saved = []
        self.append_calls = []
        self.page = page or []
        self.total = total
        self.page_calls = []
        self.count_calls = []
        self.history_page_calls = []
        self.history_page = object()

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

    def get_history_page(self, repository_session_id, *, before=None, limit):
        self.history_page_calls.append({"repository_session_id": repository_session_id, "before": before, "limit": limit})
        return self.history_page

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
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())

    result = service.list_sessions(user=_user(user_id), repository_id=None, skip=10, limit=20)

    assert [session.id for session in result.data] == [sessions[0].id]
    assert result.count == 5
    assert session_store.page_calls == [{"skip": 10, "limit": 20, "user_id": user_id, "repository_id": None}]
    assert session_store.count_calls == [{"user_id": user_id, "repository_id": None}]


def test_superuser_list_bypasses_owner_scoping() -> None:
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())
    superuser = User(id=uuid.uuid4(), email="root@example.com", hashed_password="not-used", is_superuser=True)

    service.list_sessions(user=superuser, repository_id=None, skip=0, limit=100)

    assert session_store.page_calls[0]["user_id"] is None
    assert session_store.count_calls[0]["user_id"] is None


def test_filtered_list_validates_then_passes_repository_id_to_the_store() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id)
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())

    service.list_sessions(user=_user(user_id), repository_id=repository.id, skip=0, limit=100)

    assert session_store.page_calls[0]["repository_id"] == repository.id
    assert session_store.count_calls[0]["repository_id"] == repository.id


def test_filtered_list_returns_404_when_repository_is_missing() -> None:
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositoryNotFound):
        service.list_sessions(user=_user(uuid.uuid4()), repository_id=uuid.uuid4(), skip=0, limit=100)

    assert session_store.page_calls == []


def test_filtered_list_returns_403_when_caller_does_not_own_the_repository() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositoryAccessForbidden):
        service.list_sessions(user=_user(uuid.uuid4()), repository_id=repository.id, skip=0, limit=100)

    assert session_store.page_calls == []


def test_superuser_filtered_list_bypasses_repository_ownership() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())
    superuser = User(id=uuid.uuid4(), email="root@example.com", hashed_password="not-used", is_superuser=True)

    service.list_sessions(user=superuser, repository_id=repository.id, skip=0, limit=100)

    assert session_store.page_calls[0]["repository_id"] == repository.id


def test_filtered_list_does_not_enforce_repository_readiness() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id, status=RepositoryStatus.indexing)
    session_store = FakeRepositorySessionStore(page=[], total=0)
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())

    result = service.list_sessions(user=_user(user_id), repository_id=repository.id, skip=0, limit=100)

    assert result.count == 0
    assert session_store.page_calls[0]["repository_id"] == repository.id


def test_user_cannot_create_session_for_another_users_repository() -> None:
    repository = _repository(uuid.uuid4())
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositoryAccessForbidden):
        service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id), user=_user(uuid.uuid4()))

    assert session_store.saved == []


def test_user_cannot_create_session_until_repository_is_ready() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id, status=RepositoryStatus.indexing)
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositoryNotReady):
        service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id), user=_user(user_id))

    assert session_store.saved == []


def test_create_session_uses_blank_placeholder_title() -> None:
    user_id = uuid.uuid4()
    repository = _repository(user_id)
    session_store = FakeRepositorySessionStore()
    service = RepositorySessionService(session_store, FakeRepositoryStore(repository), FakeCodingRunStore(), FakeUsageRecordStore())

    created = service.create_session(session_in=RepositorySessionCreate(repository_id=repository.id, title="Client supplied title"), user=_user(user_id))

    assert created.title == "New session"
    assert session_store.saved[0].title == "New session"


def test_user_cannot_read_another_users_session_history() -> None:
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    service = RepositorySessionService(FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositorySessionAccessForbidden):
        service.get_recent_history(repository_session_id=repository_session.id, user=_user(uuid.uuid4()))


def test_history_page_delegates_to_the_store_for_an_owned_session() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    session_store = FakeRepositorySessionStore(repository_session)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())

    page = service.get_history_page(repository_session_id=repository_session.id, user=_user(user_id), before=41, limit=50)

    assert page is session_store.history_page
    assert session_store.history_page_calls == [{"repository_session_id": repository_session.id, "before": 41, "limit": 50}]


def test_history_page_returns_404_when_the_session_is_missing() -> None:
    service = RepositorySessionService(FakeRepositorySessionStore(), FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositorySessionNotFound):
        service.get_history_page(repository_session_id=uuid.uuid4(), user=_user(uuid.uuid4()), before=None, limit=50)


def test_user_cannot_page_another_users_session_history() -> None:
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    session_store = FakeRepositorySessionStore(repository_session)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())

    with pytest.raises(RepositorySessionAccessForbidden):
        service.get_history_page(repository_session_id=repository_session.id, user=_user(uuid.uuid4()), before=None, limit=50)

    assert session_store.history_page_calls == []


def test_owned_exchange_is_persisted_through_one_store_operation() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    session_store = FakeRepositorySessionStore(repository_session)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore())
    user = _user(user_id)

    service.record_exchange(repository_session_id=repository_session.id, user=user, user_message="question", assistant_message="answer")

    assert session_store.append_calls == [(repository_session.id, {"user_message": "question", "assistant_message": "answer"})]


def test_service_construction_requires_a_coding_run_store() -> None:
    with pytest.raises(TypeError):
        RepositorySessionService(FakeRepositorySessionStore(), FakeRepositoryStore(None))  # type: ignore[call-arg]


def _usage_record(repository_session: RepositorySession, session_history_id: uuid.UUID, **overrides) -> UsageRecord:
    defaults = {
        "user_id": repository_session.user_id,
        "repository_id": repository_session.repository_id,
        "repository_session_id": repository_session.id,
        "model": "gpt-4o",
        "provider": "openai",
        "node_name": "generating",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "cost": 0.01,
        "session_history_id": session_history_id,
    }
    defaults.update(overrides)
    return UsageRecord(**defaults)


def test_turn_cost_sums_cost_and_token_totals_for_an_owned_turn() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    session_history_id = uuid.uuid4()
    records = [
        _usage_record(repository_session, session_history_id, input_tokens=100, output_tokens=50, total_tokens=150, cost=0.01),
        _usage_record(repository_session, session_history_id, input_tokens=200, output_tokens=20, total_tokens=220, cost=0.02),
    ]
    session_store = FakeRepositorySessionStore(repository_session)
    usage_store = FakeUsageRecordStore(records)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), usage_store)

    cost = service.get_turn_cost(repository_session_id=repository_session.id, session_history_id=session_history_id, user=_user(user_id))

    assert cost.session_history_id == session_history_id
    assert cost.input_tokens == 300
    assert cost.output_tokens == 70
    assert cost.total_tokens == 370
    assert cost.cost == 0.03
    # The query is scoped to the owned session so records from other sessions can never be summed in.
    assert usage_store.list_calls == [{"repository_session_id": repository_session.id, "session_history_id": session_history_id}]


def test_turn_cost_is_a_well_defined_zero_when_the_turn_has_no_recorded_usage() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    session_history_id = uuid.uuid4()
    service = RepositorySessionService(
        FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore([])
    )

    cost = service.get_turn_cost(repository_session_id=repository_session.id, session_history_id=session_history_id, user=_user(user_id))

    assert (cost.cost, cost.input_tokens, cost.output_tokens, cost.total_tokens) == (0.0, 0, 0, 0)


def test_turn_cost_sums_tokens_of_an_unpriced_call_without_its_missing_cost() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    session_history_id = uuid.uuid4()
    records = [
        _usage_record(repository_session, session_history_id, total_tokens=150, cost=0.01),
        _usage_record(repository_session, session_history_id, total_tokens=90, cost=None),
    ]
    service = RepositorySessionService(
        FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore(records)
    )

    cost = service.get_turn_cost(repository_session_id=repository_session.id, session_history_id=session_history_id, user=_user(user_id))

    # The unpriced call still contributes its tokens, but only priced calls sum into the cost figure.
    assert cost.total_tokens == 240
    assert cost.cost == 0.01


def test_turn_cost_raises_not_found_for_a_missing_session() -> None:
    usage_store = FakeUsageRecordStore([])
    service = RepositorySessionService(FakeRepositorySessionStore(None), FakeRepositoryStore(None), FakeCodingRunStore(), usage_store)

    with pytest.raises(RepositorySessionNotFound):
        service.get_turn_cost(repository_session_id=uuid.uuid4(), session_history_id=uuid.uuid4(), user=_user(uuid.uuid4()))

    # Ownership is gated before any Usage Record is read.
    assert usage_store.list_calls == []


def test_turn_cost_raises_forbidden_for_a_session_the_caller_does_not_own() -> None:
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    usage_store = FakeUsageRecordStore([])
    service = RepositorySessionService(FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None), FakeCodingRunStore(), usage_store)

    with pytest.raises(RepositorySessionAccessForbidden):
        service.get_turn_cost(repository_session_id=repository_session.id, session_history_id=uuid.uuid4(), user=_user(uuid.uuid4()))

    assert usage_store.list_calls == []


def test_run_cost_sums_cost_and_token_totals_for_an_owned_code_generation_turn() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    coding_run_id = uuid.uuid4()
    records = [
        _usage_record(repository_session, None, coding_run_id=coding_run_id, input_tokens=300, output_tokens=40, total_tokens=340, cost=0.05),
        _usage_record(repository_session, None, coding_run_id=coding_run_id, input_tokens=1200, output_tokens=800, total_tokens=2000, cost=0.20),
    ]
    session_store = FakeRepositorySessionStore(repository_session)
    usage_store = FakeUsageRecordStore(records)
    service = RepositorySessionService(session_store, FakeRepositoryStore(None), FakeCodingRunStore(), usage_store)

    cost = service.get_run_cost(repository_session_id=repository_session.id, coding_run_id=coding_run_id, user=_user(user_id))

    assert cost.coding_run_id == coding_run_id
    assert cost.session_history_id is None
    assert cost.input_tokens == 1500
    assert cost.output_tokens == 840
    assert cost.total_tokens == 2340
    assert cost.cost == pytest.approx(0.25)
    # The query is scoped to the owned session so records from another session — even the same
    # coding_run_id reused elsewhere — can never be summed in.
    assert usage_store.list_calls == [{"repository_session_id": repository_session.id, "coding_run_id": coding_run_id}]


def test_run_cost_is_a_well_defined_zero_when_the_run_has_no_recorded_usage() -> None:
    user_id = uuid.uuid4()
    repository_session = RepositorySession(user_id=user_id, repository_id=uuid.uuid4())
    coding_run_id = uuid.uuid4()
    service = RepositorySessionService(
        FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None), FakeCodingRunStore(), FakeUsageRecordStore([])
    )

    cost = service.get_run_cost(repository_session_id=repository_session.id, coding_run_id=coding_run_id, user=_user(user_id))

    assert cost.coding_run_id == coding_run_id
    assert (cost.cost, cost.input_tokens, cost.output_tokens, cost.total_tokens) == (0.0, 0, 0, 0)


def test_run_cost_raises_forbidden_for_a_session_the_caller_does_not_own() -> None:
    repository_session = RepositorySession(user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    usage_store = FakeUsageRecordStore([])
    service = RepositorySessionService(FakeRepositorySessionStore(repository_session), FakeRepositoryStore(None), FakeCodingRunStore(), usage_store)

    with pytest.raises(RepositorySessionAccessForbidden):
        service.get_run_cost(repository_session_id=repository_session.id, coding_run_id=uuid.uuid4(), user=_user(uuid.uuid4()))

    # Ownership is gated before any Usage Record is read.
    assert usage_store.list_calls == []
