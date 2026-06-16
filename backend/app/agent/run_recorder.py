"""The persistence port the graph uses to record a Coding Run's lifecycle.

The unified graph stays free of the database: the ``test_generation`` branch
calls this thin port to persist the durable Coding Run (the domain record of
truth) while the checkpointer holds in-flight graph state. ``CodingRunRecorder``
is the production adapter over ``CodingRunStore``; tests substitute a fake.
"""

import uuid
from typing import Protocol

from app.enums.coding_run import CodingRunStage, CodingRunStatus
from app.persistence.coding_run_store import CodingRunStore
from app.schemas.generation import ExternalReference, GeneratedFile
from app.schemas.review import ReviewFinding


class RunRecorder(Protocol):
    """Records Coding Run lifecycle transitions for the test-generation branch."""

    def start(self, *, thread_id: str, repository_session_id: uuid.UUID) -> uuid.UUID:
        """Persist a queued Coding Run and return its id."""

    def advance(self, coding_run_id: uuid.UUID, status: CodingRunStatus) -> None:
        """Advance a Coding Run to ``status``."""

    def fail(self, coding_run_id: uuid.UUID, *, failed_stage: str, reason: str) -> None:
        """Mark a Coding Run failed at ``failed_stage`` with a sanitized ``reason``."""

    def complete(
        self, coding_run_id: uuid.UUID, *, branch: str, diff: str, generated_files: list[GeneratedFile], external_references: list[ExternalReference]
    ) -> None:
        """Persist the generated Test Patch and advance the run to awaiting review."""

    def record_review(self, coding_run_id: uuid.UUID, *, accepted: bool, findings: list[ReviewFinding]) -> None:
        """Persist Patch Review findings and advance the run to awaiting approval or changes requested."""

    def reject(self, coding_run_id: uuid.UUID) -> None:
        """Record an owner's rejection of a reviewed run, leaving its review record intact."""

    def approve(self, coding_run_id: uuid.UUID) -> None:
        """Record an owner's approval of a reviewed run after its branch is pushed."""


class CodingRunRecorder:
    """Production ``RunRecorder`` backed by the durable ``CodingRunStore``."""

    def __init__(self, store: CodingRunStore) -> None:
        self.store = store

    def start(self, *, thread_id: str, repository_session_id: uuid.UUID) -> uuid.UUID:
        run = self.store.create(repository_session_id=repository_session_id, thread_id=thread_id)
        return run.id

    def advance(self, coding_run_id: uuid.UUID, status: CodingRunStatus) -> None:
        run = self.store.get_by_id(coding_run_id)
        if run is not None:
            self.store.advance_status(run, status)

    def fail(self, coding_run_id: uuid.UUID, *, failed_stage: str, reason: str) -> None:
        run = self.store.get_by_id(coding_run_id)
        if run is not None:
            self.store.mark_failed(run, failed_stage=CodingRunStage(failed_stage), failure_reason=reason)

    def complete(
        self, coding_run_id: uuid.UUID, *, branch: str, diff: str, generated_files: list[GeneratedFile], external_references: list[ExternalReference]
    ) -> None:
        run = self.store.get_by_id(coding_run_id)
        if run is not None:
            self.store.complete(
                run,
                generation_branch=branch,
                diff=diff,
                generated_files=[file.model_dump() for file in generated_files],
                external_references=[reference.model_dump() for reference in external_references],
            )

    def record_review(self, coding_run_id: uuid.UUID, *, accepted: bool, findings: list[ReviewFinding]) -> None:
        run = self.store.get_by_id(coding_run_id)
        if run is not None:
            self.store.record_review(run, accepted=accepted, review_findings=[finding.model_dump() for finding in findings])

    def reject(self, coding_run_id: uuid.UUID) -> None:
        run = self.store.get_by_id(coding_run_id)
        if run is not None:
            self.store.reject(run)

    def approve(self, coding_run_id: uuid.UUID) -> None:
        run = self.store.get_by_id(coding_run_id)
        if run is not None:
            self.store.approve(run)


class NullRunRecorder:
    """A no-op recorder for graph paths exercised without persistence."""

    def start(self, *, thread_id: str, repository_session_id: uuid.UUID) -> uuid.UUID:
        return uuid.uuid4()

    def advance(self, coding_run_id: uuid.UUID, status: CodingRunStatus) -> None:
        return None

    def fail(self, coding_run_id: uuid.UUID, *, failed_stage: str, reason: str) -> None:
        return None

    def complete(
        self, coding_run_id: uuid.UUID, *, branch: str, diff: str, generated_files: list[GeneratedFile], external_references: list[ExternalReference]
    ) -> None:
        return None

    def record_review(self, coding_run_id: uuid.UUID, *, accepted: bool, findings: list[ReviewFinding]) -> None:
        return None

    def reject(self, coding_run_id: uuid.UUID) -> None:
        return None

    def approve(self, coding_run_id: uuid.UUID) -> None:
        return None
