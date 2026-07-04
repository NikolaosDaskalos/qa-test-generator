"""Test Usage Record persistence behavior."""

import uuid

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db.models import CodingRun, Repository, RepositorySession, SessionHistory, UsageRecord, User
from app.db.persistence import UsageRecordStore
from app.enums import SessionMessageRole


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    User.__table__.create(engine)
    Repository.__table__.create(engine)
    RepositorySession.__table__.create(engine)
    SessionHistory.__table__.create(engine)
    CodingRun.__table__.create(engine)
    UsageRecord.__table__.create(engine)
    return engine


def _seed(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    session_id = uuid.uuid4()
    db.add(User(id=user_id, email="owner@example.com", hashed_password="not-used"))
    db.add(Repository(id=repository_id, user_id=user_id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai"))
    db.add(RepositorySession(id=session_id, user_id=user_id, repository_id=repository_id))
    db.commit()
    return user_id, repository_id, session_id


def test_create_persists_a_usage_record_with_its_metered_usage_and_attribution() -> None:
    engine = _engine()
    with Session(engine) as db:
        user_id, repository_id, session_id = _seed(db)
        store = UsageRecordStore(db)

        record = store.create(
            user_id=user_id,
            repository_id=repository_id,
            repository_session_id=session_id,
            model="claude-sonnet-4-6",
            provider="anthropic",
            node_name="generate_patch",
            input_tokens=1200,
            output_tokens=350,
            total_tokens=1550,
            cost=0.0123,
        )

        assert record.id is not None
        assert record.created_at is not None

        [reloaded] = store.list(repository_session_id=session_id)
        assert reloaded.user_id == user_id
        assert reloaded.repository_id == repository_id
        assert reloaded.repository_session_id == session_id
        assert reloaded.model == "claude-sonnet-4-6"
        assert reloaded.provider == "anthropic"
        assert reloaded.node_name == "generate_patch"
        assert reloaded.input_tokens == 1200
        assert reloaded.output_tokens == 350
        assert reloaded.total_tokens == 1550
        assert reloaded.cost == 0.0123
        assert reloaded.session_history_id is None
        assert reloaded.coding_run_id is None


def test_create_persists_a_null_cost_for_an_unpriced_model() -> None:
    engine = _engine()
    with Session(engine) as db:
        user_id, repository_id, session_id = _seed(db)
        store = UsageRecordStore(db)

        store.create(
            user_id=user_id,
            repository_id=repository_id,
            repository_session_id=session_id,
            model="some-unpriced-model",
            provider="anthropic",
            node_name="generate_patch",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost=None,
        )

        [reloaded] = store.list(repository_session_id=session_id)
        assert reloaded.cost is None


def _record_kwargs(user_id: uuid.UUID, repository_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    return {
        "user_id": user_id,
        "repository_id": repository_id,
        "repository_session_id": session_id,
        "model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "node_name": "generate_patch",
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cost": 0.001,
    }


def test_list_filters_records_by_each_attribution() -> None:
    engine = _engine()
    with Session(engine) as db:
        user_id, repository_id, session_id = _seed(db)

        other_user_id = uuid.uuid4()
        other_repository_id = uuid.uuid4()
        other_session_id = uuid.uuid4()
        db.add(User(id=other_user_id, email="other@example.com", hashed_password="not-used"))
        db.add(Repository(id=other_repository_id, user_id=other_user_id, name="other", repository_url="https://github.com/other/other.git", owner="other"))
        db.add(RepositorySession(id=other_session_id, user_id=other_user_id, repository_id=other_repository_id))

        history = SessionHistory(session_id=session_id, role=SessionMessageRole.user, content="add a test", position=1)
        run = CodingRun(repository_session_id=session_id, thread_id="thread-usage")
        db.add(history)
        db.add(run)
        db.commit()

        store = UsageRecordStore(db)
        mine = store.create(**_record_kwargs(user_id, repository_id, session_id))
        on_question = store.create(**_record_kwargs(user_id, repository_id, session_id), session_history_id=history.id)
        on_run = store.create(**_record_kwargs(user_id, repository_id, session_id), coding_run_id=run.id)
        store.create(**_record_kwargs(other_user_id, other_repository_id, other_session_id))

        assert {r.id for r in store.list(user_id=user_id)} == {mine.id, on_question.id, on_run.id}
        assert {r.id for r in store.list(repository_id=repository_id)} == {mine.id, on_question.id, on_run.id}
        assert {r.id for r in store.list(repository_session_id=session_id)} == {mine.id, on_question.id, on_run.id}
        assert [r.id for r in store.list(session_history_id=history.id)] == [on_question.id]
        assert [r.id for r in store.list(coding_run_id=run.id)] == [on_run.id]
        assert [r.id for r in store.list(user_id=other_user_id)] == [r.id for r in store.list(repository_session_id=other_session_id)]
