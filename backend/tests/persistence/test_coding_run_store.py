"""Test Coding Run persistence behavior."""

import uuid

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db.models import CodingRun, Repository, RepositorySession, User
from app.db.persistence import CodingRunStore
from app.enums import CodingRunStage, CodingRunStatus
from app.schemas import ExternalReference, GeneratedFile, ReviewFinding


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
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    session_id = uuid.uuid4()
    db.add(User(id=user_id, email="owner@example.com", hashed_password="not-used"))
    db.add(Repository(id=repository_id, user_id=user_id, name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai"))
    db.add(RepositorySession(id=session_id, user_id=user_id, repository_id=repository_id))
    db.commit()
    return session_id


def test_start_persists_a_queued_coding_run_and_returns_its_id() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)

        run_id = store.start(repository_session_id=session_id, thread_id="thread-123")

        reloaded = store.get_by_id(run_id)
        assert reloaded is not None
        assert reloaded.repository_session_id == session_id
        assert reloaded.status == CodingRunStatus.queued
        assert reloaded.thread_id == "thread-123"
        assert reloaded.failed_stage is None
        assert reloaded.failure_reason is None
        assert reloaded.revision_count == 0


def test_advance_to_moves_a_run_through_the_named_working_stages() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-abc")

        for status in (CodingRunStatus.planning, CodingRunStatus.retrieving, CodingRunStatus.generating, CodingRunStatus.reviewing):
            store.advance_to(run_id, status)
            assert store.get_by_id(run_id).status == status


def test_advance_to_on_an_unknown_run_is_a_silent_no_op() -> None:
    engine = _engine()
    with Session(engine) as db:
        _seed(db)
        store = CodingRunStore(db)

        # A missing run must not raise — the graph's persistence port stays a no-op off the happy path.
        store.advance_to(uuid.uuid4(), CodingRunStatus.planning)


def test_fail_records_failure_stage_and_sanitized_reason() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-fail")

        store.fail(run_id, failed_stage=CodingRunStage.planning, reason="Request is out of scope for code generation")

        reloaded = store.get_by_id(run_id)
        assert reloaded.status == CodingRunStatus.failed
        assert reloaded.failed_stage == CodingRunStage.planning
        assert reloaded.failure_reason == "Request is out of scope for code generation"


def test_complete_serializes_the_patch_and_advances_to_awaiting_review() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-done")

        store.complete(
            run_id,
            branch="qa-tests/abc123",
            diff="diff --git a/tests/test_x.py b/tests/test_x.py",
            generated_files=[GeneratedFile(path="tests/test_x.py", content="def test_x(): ...")],
            external_references=[ExternalReference(url="https://docs.pytest.org", title="pytest")],
        )

        reloaded = store.get_by_id(run_id)
        assert reloaded.status == CodingRunStatus.awaiting_review
        assert reloaded.generation_branch == "qa-tests/abc123"
        assert reloaded.diff.startswith("diff --git")
        assert reloaded.generated_files == [{"path": "tests/test_x.py", "content": "def test_x(): ..."}]
        assert reloaded.external_references == [{"url": "https://docs.pytest.org", "title": "pytest"}]


def test_record_review_accepted_advances_to_awaiting_approval_and_awaits_a_decision() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-review-ok")
        assert store.get_by_id(run_id).awaiting_decision is False

        store.record_review(run_id, accepted=True, findings=[ReviewFinding(category="readability", detail="clear and idiomatic")])

        reloaded = store.get_by_id(run_id)
        assert reloaded.status == CodingRunStatus.awaiting_approval
        assert reloaded.review_findings == [{"category": "readability", "detail": "clear and idiomatic"}]
        # An accepted review pauses the run for the owner's approve/reject decision.
        assert reloaded.awaiting_decision is True


def _complete_and_review(store: CodingRunStore, run_id: uuid.UUID) -> None:
    store.complete(
        run_id,
        branch="qa-tests/abc123",
        diff="diff --git a/tests/test_x.py b/tests/test_x.py",
        generated_files=[GeneratedFile(path="tests/test_x.py", content="def test_x(): ...")],
        external_references=[ExternalReference(url="https://docs.pytest.org", title="pytest")],
    )
    store.record_review(run_id, accepted=True, findings=[ReviewFinding(category="readability", detail="clear and idiomatic")])


def test_reject_marks_a_run_rejected_and_preserves_its_review_record() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-reject")
        _complete_and_review(store, run_id)

        store.reject(run_id)

        reloaded = store.get_by_id(run_id)
        assert reloaded.status == CodingRunStatus.rejected
        assert reloaded.awaiting_decision is False
        # The persisted review record is preserved for inspection even though the patch is discarded.
        assert reloaded.review_findings == [{"category": "readability", "detail": "clear and idiomatic"}]
        assert reloaded.diff.startswith("diff --git")
        assert reloaded.generated_files == [{"path": "tests/test_x.py", "content": "def test_x(): ..."}]
        assert reloaded.generation_branch == "qa-tests/abc123"


def test_approve_marks_a_run_approved_and_preserves_its_review_record() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-approve")
        _complete_and_review(store, run_id)

        store.approve(run_id, pull_request_url="https://github.com/o/r/pull/7")

        reloaded = store.get_by_id(run_id)
        assert reloaded.status == CodingRunStatus.approved
        assert reloaded.awaiting_decision is False
        # The opened Pull Request URL is persisted so the approved card can link to it on reload.
        assert reloaded.pull_request_url == "https://github.com/o/r/pull/7"
        # The persisted review record and the patch are preserved for inspection.
        assert reloaded.review_findings == [{"category": "readability", "detail": "clear and idiomatic"}]
        assert reloaded.generation_branch == "qa-tests/abc123"
        assert reloaded.diff.startswith("diff --git")


def test_record_review_rejected_advances_to_changes_requested_but_still_awaits_a_decision() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-review-no")

        store.record_review(run_id, accepted=False, findings=[ReviewFinding(category="coverage", detail="missing unhappy-path test")])

        reloaded = store.get_by_id(run_id)
        assert reloaded.status == CodingRunStatus.changes_requested
        assert reloaded.review_findings == [{"category": "coverage", "detail": "missing unhappy-path test"}]
        # A below-threshold review persists as changes_requested but still escalates to the owner.
        assert reloaded.awaiting_decision is True


def test_record_no_changes_marks_a_run_succeeded() -> None:
    engine = _engine()
    with Session(engine) as db:
        session_id = _seed(db)
        store = CodingRunStore(db)
        run_id = store.start(repository_session_id=session_id, thread_id="thread-no-changes")

        store.record_no_changes(run_id)

        assert store.get_by_id(run_id).status == CodingRunStatus.succeeded
