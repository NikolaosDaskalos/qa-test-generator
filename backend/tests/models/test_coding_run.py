"""Test Coding Run model fields and ownership relationships."""

import uuid

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.enums.coding_run import CodingRunStatus
from app.models.coding_run import CodingRun
from app.models.repository import Repository
from app.models.session import RepositorySession
from app.models.user import User


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


def test_coding_run_exposes_ownership_and_failure_vocabulary() -> None:
    for field in ("repository_session_id", "status", "thread_id", "failed_stage", "failure_reason", "revision_count"):
        assert field in CodingRun.model_fields


def test_coding_run_is_reachable_from_its_session_and_its_repository_through_it() -> None:
    engine = _engine()
    with Session(engine) as db:
        owner = User(id=uuid.uuid4(), email="owner@example.com", hashed_password="not-used")
        repository = Repository(id=uuid.uuid4(), user_id=owner.id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai")
        repository_session = RepositorySession(id=uuid.uuid4(), owner_id=owner.id, repository_id=repository.id)
        db.add_all([owner, repository, repository_session])
        db.commit()

        run = CodingRun(repository_session_id=repository_session.id, thread_id="thread-rel", status=CodingRunStatus.queued)
        db.add(run)
        db.commit()
        db.refresh(repository_session)

        assert [r.id for r in repository_session.coding_runs] == [run.id]
        assert run.repository_session.id == repository_session.id
        # The owning Repository is reached through the session, not duplicated on the run.
        assert run.repository_session.repository_id == repository.id
