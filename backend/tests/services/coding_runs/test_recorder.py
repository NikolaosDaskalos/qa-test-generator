"""The production recorder persists Coding Run lifecycle through the store."""

import uuid

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db.models import CodingRun, Repository, RepositorySession, User
from app.db.persistence import CodingRunStore
from app.enums import CodingRunStage, CodingRunStatus
from app.schemas import ExternalReference, GeneratedFile, ReviewFinding
from app.services.coding_runs.recorder import CodingRunRecorder


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    for model in (User, Repository, RepositorySession, CodingRun):
        model.__table__.create(engine)
    return engine


def _seed(db: Session):
    user_id, repository_id, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db.add(User(id=user_id, email="o@example.com", hashed_password="x"))
    db.add(Repository(id=repository_id, user_id=user_id, name="r", repository_url="https://github.com/o/r.git", owner="o"))
    db.add(RepositorySession(id=session_id, user_id=user_id, repository_id=repository_id))
    db.commit()
    return session_id


def test_recorder_starts_and_transitions_through_the_named_stages() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)

        run_id = recorder.start(thread_id="t-1", repository_session_id=session_id)
        assert store.get_by_id(run_id).status == CodingRunStatus.queued

        recorder.begin_planning(run_id)
        assert store.get_by_id(run_id).status == CodingRunStatus.planning

        recorder.begin_retrieving(run_id)
        assert store.get_by_id(run_id).status == CodingRunStatus.retrieving

        recorder.begin_generating(run_id)
        assert store.get_by_id(run_id).status == CodingRunStatus.generating

        recorder.begin_reviewing(run_id)
        assert store.get_by_id(run_id).status == CodingRunStatus.reviewing


def test_recorder_fails_a_run_at_a_typed_stage() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)

        run_id = recorder.start(thread_id="t-1", repository_session_id=session_id)
        recorder.fail(run_id, failed_stage=CodingRunStage.planning, reason="Out of scope")

        failed = store.get_by_id(run_id)
        assert failed.status == CodingRunStatus.failed
        assert failed.failed_stage == CodingRunStage.planning
        assert failed.failure_reason == "Out of scope"


def test_recorder_persists_git_push_failures() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-push-fail", repository_session_id=session_id)

        recorder.fail(run_id, failed_stage=CodingRunStage.git_push, reason="Could not push the approved Test Patch branch.")

        failed = store.get_by_id(run_id)
        assert failed.status == CodingRunStatus.failed
        assert failed.failed_stage == CodingRunStage.git_push
        assert failed.failure_reason == "Could not push the approved Test Patch branch."


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


def test_recorder_records_an_accepted_review_through_the_store() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-review", repository_session_id=session_id)

        recorder.record_review(run_id, accepted=True, findings=[ReviewFinding(category="conventions", detail="matches existing tests")])

        reviewed = store.get_by_id(run_id)
        assert reviewed.status == CodingRunStatus.awaiting_approval
        assert reviewed.review_findings == [{"category": "conventions", "detail": "matches existing tests"}]


def test_recorder_rejects_a_reviewed_run_through_the_store() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-reject", repository_session_id=session_id)
        recorder.record_review(run_id, accepted=True, findings=[ReviewFinding(category="conventions", detail="matches existing tests")])

        recorder.reject(run_id)

        rejected = store.get_by_id(run_id)
        assert rejected.status == CodingRunStatus.rejected
        # The persisted review record survives the rejection for later inspection.
        assert rejected.review_findings == [{"category": "conventions", "detail": "matches existing tests"}]


def test_recorder_approves_a_reviewed_run_through_the_store() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-approve", repository_session_id=session_id)
        recorder.record_review(run_id, accepted=True, findings=[ReviewFinding(category="conventions", detail="matches existing tests")])

        recorder.approve(run_id, pull_request_url="https://github.com/o/r/pull/7")

        approved = store.get_by_id(run_id)
        assert approved.status == CodingRunStatus.approved
        # The opened Pull Request URL reaches the durable run through the recorder.
        assert approved.pull_request_url == "https://github.com/o/r/pull/7"
        # The persisted review record survives the approval for later inspection.
        assert approved.review_findings == [{"category": "conventions", "detail": "matches existing tests"}]


def test_run_awaits_a_decision_only_while_awaiting_approval() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-decide", repository_session_id=session_id)

        assert store.get_by_id(run_id).awaiting_decision is False

        recorder.record_review(run_id, accepted=True, findings=[])
        assert store.get_by_id(run_id).awaiting_decision is True

        recorder.approve(run_id, pull_request_url="https://github.com/o/r/pull/7")
        assert store.get_by_id(run_id).awaiting_decision is False


def test_recorder_records_a_rejected_review_as_changes_requested() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        recorder = CodingRunRecorder(store)
        run_id = recorder.start(thread_id="t-review-no", repository_session_id=session_id)

        recorder.record_review(run_id, accepted=False, findings=[ReviewFinding(category="imports", detail="unknown import")])

        reviewed = store.get_by_id(run_id)
        assert reviewed.status == CodingRunStatus.changes_requested
        assert reviewed.review_findings == [{"category": "imports", "detail": "unknown import"}]
