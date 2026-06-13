"""Test Repository Session persistence behavior."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import NullPool, StaticPool
from sqlmodel import Session, create_engine, delete, select

from app.core.config import settings
from app.enums.repository import RepositoryProvider
from app.enums.session import SessionMessageRole
from app.models.repository import Repository
from app.models.session import RepositorySession, SessionHistory
from app.models.user import User
from app.persistence.session_store import RepositorySessionStore


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    User.__table__.create(engine)
    Repository.__table__.create(engine)
    RepositorySession.__table__.create(engine)
    SessionHistory.__table__.create(engine)
    return engine


def test_recent_history_returns_latest_six_messages_in_chronological_order() -> None:
    engine = _engine()
    owner_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    repository_session_id = uuid.uuid4()

    with Session(engine) as db:
        db.add(User(id=owner_id, email="owner@example.com", hashed_password="not-used"))
        db.add(
            Repository(id=repository_id, user_id=owner_id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai")
        )
        db.add(RepositorySession(id=repository_session_id, owner_id=owner_id, repository_id=repository_id))
        db.commit()
        store = RepositorySessionStore(db)

        for number in range(1, 5):
            store.append_exchange(repository_session_id, user_message=f"question {number}", assistant_message=f"answer {number}")

        messages = store.get_recent_history(repository_session_id)

    assert [(message.role, message.content) for message in messages] == [
        (SessionMessageRole.user, "question 2"),
        (SessionMessageRole.assistant, "answer 2"),
        (SessionMessageRole.user, "question 3"),
        (SessionMessageRole.assistant, "answer 3"),
        (SessionMessageRole.user, "question 4"),
        (SessionMessageRole.assistant, "answer 4"),
    ]


def test_append_exchange_locks_repository_session_before_allocating_positions() -> None:
    repository_session_id = uuid.uuid4()
    executed_statements = []

    class RecordingSession:
        def exec(self, statement):
            executed_statements.append(statement)
            result = type("Result", (), {"one": lambda self: repository_session_id if len(executed_statements) == 1 else None})()
            return result

        def add(self, _instance) -> None:
            pass

        def commit(self) -> None:
            pass

        def refresh(self, _instance) -> None:
            pass

    store = RepositorySessionStore(RecordingSession())  # type: ignore[arg-type]

    store.append_exchange(repository_session_id, user_message="question", assistant_message="answer")

    statements = [str(statement.compile(dialect=postgresql.dialect())) for statement in executed_statements]
    assert "FOR UPDATE" in statements[0]
    assert "repository_session" in statements[0]
    assert "max(session_history.position)" in statements[1]


def test_repository_binding_cannot_be_reassigned_after_session_creation() -> None:
    engine = _engine()
    owner_id = uuid.uuid4()
    first_repository = Repository(user_id=owner_id, name="first", repository_url="https://github.com/example/first.git", owner="example")
    second_repository = Repository(user_id=owner_id, name="second", repository_url="https://github.com/example/second.git", owner="example")
    repository_session = RepositorySession(owner_id=owner_id, repository_id=first_repository.id)

    with Session(engine) as db:
        db.add(User(id=owner_id, email="owner@example.com", hashed_password="not-used"))
        db.add(first_repository)
        db.add(second_repository)
        db.add(repository_session)
        db.commit()

        repository_session.repository_id = second_repository.id
        with pytest.raises(ValueError, match="Repository Session binding is immutable"):
            db.commit()


def test_deleting_repository_cascades_to_sessions_and_history() -> None:
    engine = _engine()
    owner = User(email="owner@example.com", hashed_password="not-used")
    repository = Repository(user_id=owner.id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai")
    repository_session = RepositorySession(owner_id=owner.id, repository_id=repository.id)
    history = SessionHistory(session_id=repository_session.id, role=SessionMessageRole.user, content="question", position=1)
    repository_session_id = repository_session.id

    with Session(engine) as db:
        db.add(owner)
        db.add(repository)
        db.add(repository_session)
        db.add(history)
        db.commit()

        db.exec(delete(Repository).where(Repository.id == repository.id))
        db.commit()

        assert db.get(RepositorySession, repository_session_id) is None
        assert db.exec(select(SessionHistory).where(SessionHistory.session_id == repository_session_id)).all() == []


def test_concurrent_appends_allocate_unique_ordered_positions_in_postgresql() -> None:
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI), poolclass=NullPool)
    if engine.dialect.name != "postgresql":
        pytest.skip("Repository Session locking is tested against PostgreSQL")

    owner = User(email=f"session-lock-{uuid.uuid4()}@example.com", hashed_password="not-used")
    repository = Repository(
        user_id=owner.id,
        name="session-lock-test",
        repository_url=f"https://github.com/example/session-lock-{uuid.uuid4()}.git",
        provider=RepositoryProvider.github,
        owner="example",
    )
    repository_session = RepositorySession(owner_id=owner.id, repository_id=repository.id)
    owner_id = owner.id
    repository_session_id = repository_session.id

    with Session(engine) as db:
        db.add(owner)
        db.add(repository)
        db.add(repository_session)
        db.commit()

    max_position_barrier = threading.Barrier(2)

    @event.listens_for(engine, "after_cursor_execute")
    def synchronize_unlocked_position_reads(connection, _cursor, statement, _parameters, _context, _executemany) -> None:
        normalized = " ".join(statement.lower().split())
        if "from repository_session" in normalized and "for update" in normalized:
            connection.info["repository_session_locked"] = True
        if "max(session_history.position)" in normalized and not connection.info.get("repository_session_locked"):
            max_position_barrier.wait(timeout=5)

    def append(number: int) -> None:
        with Session(engine) as db:
            RepositorySessionStore(db).append_exchange(repository_session_id, user_message=f"question {number}", assistant_message=f"answer {number}")

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(append, number) for number in (1, 2)]
            for future in futures:
                future.result(timeout=10)

        with Session(engine) as db:
            positions = db.exec(
                select(SessionHistory.position).where(SessionHistory.session_id == repository_session_id).order_by(SessionHistory.position)
            ).all()

        assert positions == [1, 2, 3, 4]
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_unlocked_position_reads)
        with Session(engine) as db:
            db.exec(delete(User).where(User.id == owner_id))
            db.commit()
        engine.dispose()
