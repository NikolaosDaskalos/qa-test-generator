"""The PostgreSQL store for Coding Run lifecycle records.

The store is the graph's durable persistence port: the ``code_generation`` branch
calls it by ``coding_run_id`` to record a run's lifecycle while the checkpointer
holds in-flight graph state. The store owns the id lookup, the missing-run guard
(a run absent off the happy path is a silent no-op), and the serialization of the
Test Patch and review findings — so the graph stays free of the database and no
translation layer sits between them. Tests substitute a fake at the same seam.
"""

import uuid
from collections.abc import Callable

from sqlmodel import Session

from app.db.models import CodingRun
from app.enums import CodingRunStage, CodingRunStatus
from app.schemas import ExternalReference, GeneratedFile, ReviewFinding


class CodingRunStore:
    """Persist Coding Runs through a SQLModel session, keyed by id."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def start(self, *, repository_session_id: uuid.UUID, thread_id: str) -> uuid.UUID:
        """Insert a new queued run keyed to its graph ``thread_id`` and return its id."""
        run = CodingRun(repository_session_id=repository_session_id, thread_id=thread_id, status=CodingRunStatus.queued)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run.id

    def get_by_id(self, coding_run_id: uuid.UUID) -> CodingRun | None:
        """Load a run by id, or ``None`` if absent."""
        return self.session.get(CodingRun, coding_run_id)

    def advance_to(self, coding_run_id: uuid.UUID, status: CodingRunStatus) -> None:
        """Move a run to the next lifecycle ``status``."""
        self._mutate(coding_run_id, lambda run: setattr(run, "status", status))

    def record_no_changes(self, coding_run_id: uuid.UUID) -> None:
        """Record a run that proposed no test changes across all attempts as succeeded."""
        self.advance_to(coding_run_id, CodingRunStatus.succeeded)

    def fail(self, coding_run_id: uuid.UUID, *, failed_stage: CodingRunStage, reason: str) -> None:
        """Fail a run, recording the stage and a user-safe reason."""

        def mutate(run: CodingRun) -> None:
            run.status = CodingRunStatus.failed
            run.failed_stage = failed_stage
            run.failure_reason = reason

        self._mutate(coding_run_id, mutate)

    def complete(
        self, coding_run_id: uuid.UUID, *, branch: str, diff: str, generated_files: list[GeneratedFile], external_references: list[ExternalReference]
    ) -> None:
        """Serialize and store the built Test Patch and move the run to awaiting review."""

        def mutate(run: CodingRun) -> None:
            run.status = CodingRunStatus.awaiting_review
            run.generation_branch = branch
            run.diff = diff
            run.generated_files = [file.model_dump() for file in generated_files]
            run.external_references = [reference.model_dump() for reference in external_references]

        self._mutate(coding_run_id, mutate)

    def record_review(self, coding_run_id: uuid.UUID, *, accepted: bool, findings: list[ReviewFinding]) -> None:
        """Serialize and store the review findings, moving to awaiting approval or changes requested."""

        def mutate(run: CodingRun) -> None:
            run.status = CodingRunStatus.awaiting_approval if accepted else CodingRunStatus.changes_requested
            run.review_findings = [finding.model_dump() for finding in findings]

        self._mutate(coding_run_id, mutate)

    def reject(self, coding_run_id: uuid.UUID) -> None:
        """Mark a reviewed run rejected, leaving its persisted review record intact."""
        self._mutate(coding_run_id, lambda run: setattr(run, "status", CodingRunStatus.rejected))

    def approve(self, coding_run_id: uuid.UUID, *, pull_request_url: str) -> None:
        """Mark a reviewed run approved and store the opened Pull Request URL, leaving its pushed patch record intact."""

        def mutate(run: CodingRun) -> None:
            run.status = CodingRunStatus.approved
            run.pull_request_url = pull_request_url

        self._mutate(coding_run_id, mutate)

    def _mutate(self, coding_run_id: uuid.UUID, mutate: Callable[[CodingRun], None]) -> None:
        """Apply ``mutate`` to the loaded run and persist it; a missing run is a silent no-op."""
        run = self.session.get(CodingRun, coding_run_id)
        if run is None:
            return
        mutate(run)
        self.session.add(run)
        self.session.commit()
