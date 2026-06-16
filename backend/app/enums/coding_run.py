from enum import Enum


class CodingRunStatus(str, Enum):
    """The lifecycle states of a Coding Run.

    This issue drives a run through ``queued -> planning -> retrieving`` and to
    ``failed`` on a rejected scope; the later states are the planned vocabulary
    that subsequent stages (generation, review, application) advance into.
    """

    queued = "queued"
    planning = "planning"
    retrieving = "retrieving"
    generating = "generating"
    awaiting_review = "awaiting_review"
    reviewing = "reviewing"
    awaiting_approval = "awaiting_approval"
    changes_requested = "changes_requested"
    succeeded = "succeeded"
    failed = "failed"


class CodingRunStage(str, Enum):
    """A working stage a Coding Run can fail at, recorded as ``failed_stage``."""

    planning = "planning"
    retrieving = "retrieving"
    generating = "generating"
    reviewing = "reviewing"
