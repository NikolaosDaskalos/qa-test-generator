"""The PostgreSQL store for Coding Run lifecycle records."""

import uuid

from sqlmodel import Session

from app.enums import CodingRunStage, CodingRunStatus
from app.models import CodingRun


class CodingRunStore:
    """Persist Coding Runs through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, repository_session_id: uuid.UUID, thread_id: str) -> CodingRun:
        """Insert a new queued run keyed to its graph ``thread_id``."""
        run = CodingRun(repository_session_id=repository_session_id, thread_id=thread_id, status=CodingRunStatus.queued)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_by_id(self, coding_run_id: uuid.UUID) -> CodingRun | None:
        """Load a run by id, or ``None`` if absent."""
        return self.session.get(CodingRun, coding_run_id)

    def advance_status(self, coding_run: CodingRun, status: CodingRunStatus) -> CodingRun:
        """Move a run to the next lifecycle ``status``."""
        coding_run.status = status
        self.session.add(coding_run)
        self.session.commit()
        self.session.refresh(coding_run)
        return coding_run

    def mark_failed(self, coding_run: CodingRun, *, failed_stage: CodingRunStage, failure_reason: str) -> CodingRun:
        """Fail a run, recording the stage and a user-safe reason."""
        coding_run.status = CodingRunStatus.failed
        coding_run.failed_stage = failed_stage
        coding_run.failure_reason = failure_reason
        self.session.add(coding_run)
        self.session.commit()
        self.session.refresh(coding_run)
        return coding_run

    def complete(self, coding_run: CodingRun, *, generation_branch: str, diff: str, generated_files: list, external_references: list) -> CodingRun:
        """Store the built Test Patch and move the run to awaiting review."""
        coding_run.status = CodingRunStatus.awaiting_review
        coding_run.generation_branch = generation_branch
        coding_run.diff = diff
        coding_run.generated_files = generated_files
        coding_run.external_references = external_references
        self.session.add(coding_run)
        self.session.commit()
        self.session.refresh(coding_run)
        return coding_run

    def reject(self, coding_run: CodingRun) -> CodingRun:
        """Mark a reviewed run rejected, leaving its persisted review record intact."""
        coding_run.status = CodingRunStatus.rejected
        self.session.add(coding_run)
        self.session.commit()
        self.session.refresh(coding_run)
        return coding_run

    def approve(self, coding_run: CodingRun) -> CodingRun:
        """Mark a reviewed run approved, leaving its pushed patch record intact."""
        coding_run.status = CodingRunStatus.approved
        self.session.add(coding_run)
        self.session.commit()
        self.session.refresh(coding_run)
        return coding_run

    def record_review(self, coding_run: CodingRun, *, accepted: bool, review_findings: list) -> CodingRun:
        """Store the review findings, moving to awaiting approval or changes requested."""
        coding_run.status = CodingRunStatus.awaiting_approval if accepted else CodingRunStatus.changes_requested
        coding_run.review_findings = review_findings
        self.session.add(coding_run)
        self.session.commit()
        self.session.refresh(coding_run)
        return coding_run
