"""Test the owner-scoped AI Cost rollup service (ADR-0014)."""

import uuid

import pytest

from app.core.errors.repository_errors import RepositoryAccessForbidden, RepositoryNotFound
from app.core.errors.session_errors import RepositorySessionAccessForbidden, RepositorySessionNotFound
from app.db.models import Repository, RepositorySession, User
from app.db.persistence import CostTotals
from app.services import CostRollupService


class FakeSessionStore:
    def __init__(self, repository_session: RepositorySession | None = None) -> None:
        self.repository_session = repository_session

    def get_by_id(self, repository_session_id):
        if self.repository_session and self.repository_session.id == repository_session_id:
            return self.repository_session
        return None


class FakeRepositoryStore:
    def __init__(self, repository: Repository | None = None) -> None:
        self.repository = repository

    def get_by_id(self, repository_id):
        if self.repository and self.repository.id == repository_id:
            return self.repository
        return None


class FakeUsageRecordStore:
    def __init__(self, totals: CostTotals) -> None:
        self._totals = totals
        self.totals_calls = []

    def totals(self, **kwargs) -> CostTotals:
        self.totals_calls.append(kwargs)
        return self._totals


def _user(user_id: uuid.UUID, *, is_superuser: bool = False) -> User:
    return User(id=user_id, email=f"{user_id}@example.com", hashed_password="not-used", is_superuser=is_superuser)


def _service(*, session=None, repository=None, totals=None):
    usage_store = FakeUsageRecordStore(totals or CostTotals(cost=0.03, input_tokens=400, output_tokens=70, total_tokens=470))
    return CostRollupService(FakeSessionStore(session), FakeRepositoryStore(repository), usage_store), usage_store


def test_session_rollup_returns_the_session_scoped_total_for_its_owner() -> None:
    owner_id = uuid.uuid4()
    session = RepositorySession(id=uuid.uuid4(), user_id=owner_id, repository_id=uuid.uuid4())
    service, usage_store = _service(session=session)

    result = service.session_rollup(repository_session_id=session.id, user=_user(owner_id))

    assert result.cost == 0.03
    assert result.input_tokens == 400
    assert result.output_tokens == 70
    assert result.total_tokens == 470
    assert usage_store.totals_calls == [{"repository_session_id": session.id}]


def test_session_rollup_refuses_a_session_owned_by_another_user() -> None:
    session = RepositorySession(id=uuid.uuid4(), user_id=uuid.uuid4(), repository_id=uuid.uuid4())
    service, usage_store = _service(session=session)

    with pytest.raises(RepositorySessionAccessForbidden):
        service.session_rollup(repository_session_id=session.id, user=_user(uuid.uuid4()))
    assert usage_store.totals_calls == []


def test_session_rollup_404s_on_a_missing_session() -> None:
    service, usage_store = _service(session=None)

    with pytest.raises(RepositorySessionNotFound):
        service.session_rollup(repository_session_id=uuid.uuid4(), user=_user(uuid.uuid4()))
    assert usage_store.totals_calls == []


def test_repository_rollup_returns_the_repository_scoped_total_for_its_owner() -> None:
    owner_id = uuid.uuid4()
    repository = Repository(id=uuid.uuid4(), user_id=owner_id, name="r", repository_url="https://github.com/o/r.git", owner="o")
    service, usage_store = _service(repository=repository)

    result = service.repository_rollup(repository_id=repository.id, user=_user(owner_id))

    assert result.total_tokens == 470
    assert usage_store.totals_calls == [{"repository_id": repository.id}]


def test_repository_rollup_refuses_a_repository_owned_by_another_user() -> None:
    repository = Repository(id=uuid.uuid4(), user_id=uuid.uuid4(), name="r", repository_url="https://github.com/o/r.git", owner="o")
    service, usage_store = _service(repository=repository)

    with pytest.raises(RepositoryAccessForbidden):
        service.repository_rollup(repository_id=repository.id, user=_user(uuid.uuid4()))
    assert usage_store.totals_calls == []


def test_repository_rollup_404s_on_a_missing_repository() -> None:
    service, usage_store = _service(repository=None)

    with pytest.raises(RepositoryNotFound):
        service.repository_rollup(repository_id=uuid.uuid4(), user=_user(uuid.uuid4()))
    assert usage_store.totals_calls == []


def test_user_rollup_sums_only_the_requesting_users_records() -> None:
    user_id = uuid.uuid4()
    service, usage_store = _service()

    result = service.user_rollup(user=_user(user_id))

    assert result.total_tokens == 470
    assert usage_store.totals_calls == [{"user_id": user_id}]


def test_all_users_rollup_sums_every_record_unfiltered() -> None:
    service, usage_store = _service()

    result = service.all_users_rollup()

    assert result.total_tokens == 470
    assert usage_store.totals_calls == [{}]
