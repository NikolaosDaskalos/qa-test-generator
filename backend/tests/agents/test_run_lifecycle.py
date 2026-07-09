"""The run-lifecycle seam: one operation advances the Coding Run and announces the stage.

``RunLifecycle.enter(stage, coding_run_id)`` is the single place the durable
Coding Run status advance and the Agent Stream ``Stage`` marker are paired; the
status↔marker mapping (including the divergent ``revising → generating`` and
``re_reviewing → reviewing`` rows) is data in that one module.
"""

import uuid

import pytest

from app.agents.run_lifecycle import RunLifecycle
from app.enums import CodingRunStatus
from app.schemas import Stage


class FakeRecorder:
    """Record the status advances the lifecycle performs."""

    def __init__(self) -> None:
        self.advances = []

    def advance_to(self, coding_run_id, status):
        self.advances.append((coding_run_id, status))


def test_enter_advances_the_run_and_emits_the_stage_marker() -> None:
    """Entering a stage advances the durable Coding Run status and emits the matching marker."""
    recorder = FakeRecorder()
    emitted = []
    lifecycle = RunLifecycle(recorder, emitter=emitted.append)
    coding_run_id = uuid.uuid4()

    lifecycle.enter("planning", coding_run_id)

    assert recorder.advances == [(coding_run_id, CodingRunStatus.planning)]
    assert emitted == [Stage(stage="planning")]


@pytest.mark.parametrize(
    ("stage", "status"),
    [
        ("planning", CodingRunStatus.planning),
        ("retrieving", CodingRunStatus.retrieving),
        ("generating", CodingRunStatus.generating),
        ("revising", CodingRunStatus.generating),
        ("reviewing", CodingRunStatus.reviewing),
        ("re_reviewing", CodingRunStatus.reviewing),
    ],
)
def test_every_stage_marker_advances_to_its_mapped_status(stage, status) -> None:
    """Each of the six markers advances to its mapped status and rides the wire unchanged.

    The two divergent rows are deliberate policy, held here as data: a Generation
    Retry announces ``revising`` while the durable run re-enters ``generating``,
    and its second review announces ``re_reviewing`` while the run re-enters
    ``reviewing``.
    """
    recorder = FakeRecorder()
    emitted = []
    lifecycle = RunLifecycle(recorder, emitter=emitted.append)
    coding_run_id = uuid.uuid4()

    lifecycle.enter(stage, coding_run_id)

    assert recorder.advances == [(coding_run_id, status)]
    assert emitted == [Stage(stage=stage)]
