"""The persistence port the graph uses to record a Coding Run's lifecycle.

The unified graph stays free of the database: the ``code_generation`` branch calls
this thin port by ``coding_run_id`` to persist the durable Coding Run (the domain
record of truth) while the checkpointer holds in-flight graph state. The production
adapter is ``CodingRunStore`` itself — it owns the id lookup, the missing-run guard,
and the Test Patch / review-finding serialization behind these methods. Tests
substitute a fake at the same seam.
"""

import uuid
from typing import Protocol

from app.enums import CodingRunStage, CodingRunStatus
from app.schemas import ExternalReference, GeneratedFile, ReviewFinding


class RunRecorder(Protocol):
    """Records Coding Run lifecycle transitions for the code-generation branch."""

    def start(self, *, thread_id: str, repository_session_id: uuid.UUID) -> uuid.UUID:
        """Persist a queued Coding Run and return its id."""

    def advance_to(self, coding_run_id: uuid.UUID, status: CodingRunStatus) -> None:
        """Move a Coding Run into its next working stage."""

    def fail(self, coding_run_id: uuid.UUID, *, failed_stage: CodingRunStage, reason: str) -> None:
        """Mark a Coding Run failed at ``failed_stage`` with a sanitized ``reason``."""

    def complete(
        self, coding_run_id: uuid.UUID, *, branch: str, diff: str, generated_files: list[GeneratedFile], external_references: list[ExternalReference]
    ) -> None:
        """Persist the generated Test Patch and advance the run to awaiting review."""

    def record_review(self, coding_run_id: uuid.UUID, *, accepted: bool, findings: list[ReviewFinding]) -> None:
        """Persist Patch Review findings and advance the run to awaiting approval or changes requested."""

    def reject(self, coding_run_id: uuid.UUID) -> None:
        """Record an owner's rejection of a reviewed run, leaving its review record intact."""

    def approve(self, coding_run_id: uuid.UUID, *, pull_request_url: str) -> None:
        """Record an owner's approval of a reviewed run after its branch is pushed and its Pull Request opened."""

    def record_no_changes(self, coding_run_id: uuid.UUID) -> None:
        """Record a run that proposed no test changes across all attempts as succeeded."""
