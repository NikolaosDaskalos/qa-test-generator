"""The run-lifecycle seam for the code-generation branch.

Advancing the durable Coding Run status and announcing the stage on the Agent
Stream are one operation: ``RunLifecycle.enter(stage, coding_run_id)``. The
status↔marker mapping lives here as data, so the pairing cannot drift across
nodes. This module lives at the agents layer because it speaks the wire
vocabulary (ADR-0002: emission stays at the node layer, never on the store).
"""

import uuid
from collections.abc import Callable

from app.enums import CodingRunStatus
from app.schemas import AgentStreamEvent, Stage
from app.streaming import emit

# The status each Stage marker advances the durable Coding Run to. The wire is
# finer-grained than the durable record: a Generation Retry announces ``revising``
# while the run re-enters ``generating``, and its second review announces
# ``re_reviewing`` while the run re-enters ``reviewing``.
STAGE_TO_STATUS: dict[str, CodingRunStatus] = {
    "planning": CodingRunStatus.planning,
    "retrieving": CodingRunStatus.retrieving,
    "generating": CodingRunStatus.generating,
    "revising": CodingRunStatus.generating,
    "reviewing": CodingRunStatus.reviewing,
    "re_reviewing": CodingRunStatus.reviewing,
}


class RunLifecycle:
    """Advance the Coding Run and announce the stage as one operation."""

    def __init__(self, recorder, *, emitter: Callable[[AgentStreamEvent], None] = emit) -> None:
        self._recorder = recorder
        self._emit = emitter

    def enter(self, stage: str, coding_run_id: uuid.UUID) -> None:
        """Advance the run to the stage's mapped status and emit its ``Stage`` marker."""
        self._recorder.advance_to(coding_run_id, STAGE_TO_STATUS[stage])
        self._emit(Stage(stage=stage))
