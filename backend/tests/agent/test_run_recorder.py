"""The production recorder persists Coding Run lifecycle through the store."""

import uuid

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.agent.run_recorder import CodingRunRecorder
from app.enums.coding_run import CodingRunStage, CodingRunStatus
from app.models.coding_run import CodingRun
from app.models.repository import Repository
from app.models.session import RepositorySession
from app.models.user import User
from app.persistence.coding_run_store import CodingRunStore
from app.schemas.generation import ExternalReference, GeneratedFile


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    for model in (User, Repository, RepositorySession, CodingRun):
        model.__table__.create(engine)
    return engine


def _seed(db: Session):
    owner_id, repository_id, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(User(id=owner_id, email="o@example.com", hashed_password="x"))
    db.add(Repository(id=repository_id, user_id=owner_id, name="r", repository_url="https://github.com/o/r.git", owner="o"))
    db.add(RepositorySession(id=session_id, owner_id=owner_id, repository_id=repository_id))
    db.commit()
    return session_id


def test_recorder_starts_advances_and_fails_through_the_store() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)

        run_id = recorder.start(thread_id="t-1", repository_session_id=session_id)
        assert store.get_by_id(run_id).status == CodingRunStatus.queued

        recorder.advance(run_id, CodingRunStatus.planning)
        assert store.get_by_id(run_id).status == CodingRunStatus.planning

        recorder.fail(run_id, failed_stage="planning", reason="Out of scope")
        failed = store.get_by_id(run_id)
        assert failed.status == CodingRunStatus.failed
        assert failed.failed_stage == CodingRunStage.planning
        assert failed.failure_reason == "Out of scope"


def test_recorder_completes_a_run_with_the_serialized_patch() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-done", repository_session_id=session_id)

        recorder.complete(
            run_id,
            branch="qa-tests/xyz",
            diff="diff --git a/tests/test_x.py b/tests/test_x.py",
            generated_files=[GeneratedFile(path="tests/test_x.py", content="def test_x(): ...")],
            external_references=[ExternalReference(url="https://docs.pytest.org", title="pytest")],
        )

        completed = store.get_by_id(run_id)
        assert completed.status == CodingRunStatus.awaiting_review
        assert completed.generation_branch == "qa-tests/xyz"
        assert completed.generated_files == [{"path": "tests/test_x.py", "content": "def test_x(): ..."}]
        assert completed.external_references == [{"url": "https://docs.pytest.org", "title": "pytest"}]
