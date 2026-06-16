"""Test Coding Run persistence behavior."""

import uuid

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.enums.coding_run import CodingRunStage, CodingRunStatus
from app.models.coding_run import CodingRun
from app.models.repository import Repository
from app.models.session import RepositorySession
from app.models.user import User
from app.persistence.coding_run_store import CodingRunStore


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    User.__table__.create(engine)
    Repository.__table__.create(engine)
    RepositorySession.__table__.create(engine)
    CodingRun.__table__.create(engine)
    return engine


def _seed(db: Session) -> uuid.UUID:
    owner_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    session_id = uuid.uuid4()
    db.add(User(id=owner_id, email="owner@example.com", hashed_password="not-used"))
    db.add(Repository(id=repository_id, user_id=owner_id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai"))
    db.add(RepositorySession(id=session_id, owner_id=owner_id, repository_id=repository_id))
    db.commit()
    return session_id


def test_create_persists_a_queued_coding_run_with_its_thread_id() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)

        run = store.create(repository_session_id=session_id, thread_id="thread-123")

        assert run.id is not None
        assert run.status == CodingRunStatus.queued
        assert run.thread_id == "thread-123"
        assert run.failed_stage is None
        assert run.failure_reason is None
        assert run.revision_count == 0

        reloaded = store.get_by_id(run.id)
        assert reloaded is not None
        assert reloaded.repository_session_id == session_id
        assert reloaded.status == CodingRunStatus.queued


def test_advance_status_moves_a_run_through_planning_and_retrieving() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run = store.create(repository_session_id=session_id, thread_id="thread-abc")

        store.advance_status(run, CodingRunStatus.planning)
        assert store.get_by_id(run.id).status == CodingRunStatus.planning

        store.advance_status(run, CodingRunStatus.retrieving)
        assert store.get_by_id(run.id).status == CodingRunStatus.retrieving


def test_mark_failed_records_failure_stage_and_sanitized_reason() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run = store.create(repository_session_id=session_id, thread_id="thread-fail")

        store.mark_failed(run, failed_stage=CodingRunStage.planning, failure_reason="Request is out of scope for test generation")

        reloaded = store.get_by_id(run.id)
        assert reloaded.status == CodingRunStatus.failed
        assert reloaded.failed_stage == CodingRunStage.planning
        assert reloaded.failure_reason == "Request is out of scope for test generation"


def test_complete_persists_the_patch_and_advances_to_awaiting_review() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run = store.create(repository_session_id=session_id, thread_id="thread-done")

        store.complete(
            run,
            generation_branch="qa-tests/abc123",
            diff="diff --git a/tests/test_x.py b/tests/test_x.py",
            generated_files=[{"path": "tests/test_x.py", "content": "def test_x(): ..."}],
            external_references=[{"url": "https://docs.pytest.org", "title": "pytest"}],
        )

        reloaded = store.get_by_id(run.id)
        assert reloaded.status == CodingRunStatus.awaiting_review
        assert reloaded.generation_branch == "qa-tests/abc123"
        assert reloaded.diff.startswith("diff --git")
        assert reloaded.generated_files == [{"path": "tests/test_x.py", "content": "def test_x(): ..."}]
        assert reloaded.external_references == [{"url": "https://docs.pytest.org", "title": "pytest"}]
