"""The post-review gate: the backend's one decision point after a Patch Review.

ADR-0004 splits the roles: the Code Reviewer scores, the backend decides. This
module is the single named home for "the backend decides" — ``decide`` maps a
``ReviewResult``, the Generation Retries already spent, and the resolved
``ReviewPolicy`` to one explicit verdict consumed by both the ``review_patch``
node (whether the terminal ``ReviewResult`` rides the Agent Stream) and the
post-review conditional edge (where the graph routes next).

The Generation Retries spend/limit arithmetic over the one graph-state key is
the gate's implementation detail and lives here with it: the count helpers are
exposed for the nodes that spend a retry or name their stage by it, but only
``decide`` weighs the count against the policy's budget. Exhausting the retries
is not a failure — the gate escalates the best below-threshold attempt or
reports the tests as already covering; it never fails the run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from app.schemas import ReviewResult
from app.services.coding_runs.review_policy import ReviewPolicy

ReviewVerdict = Literal["revise", "escalate", "already_covered"]

GENERATION_RETRIES_STATE_KEY = "generation_retries"


def generation_retries(state: Mapping[str, object]) -> int:
    """The number of Generation Retries already spent, read from graph state."""
    return int(state.get(GENERATION_RETRIES_STATE_KEY) or 0)


def is_generation_retry(state: Mapping[str, object]) -> bool:
    """Whether at least one Generation Retry has been spent."""
    return generation_retries(state) > 0


def spend_generation_retry(state: Mapping[str, object]) -> dict[str, int]:
    """Graph-state update that records one more spent Generation Retry."""
    return {GENERATION_RETRIES_STATE_KEY: generation_retries(state) + 1}


def decide(review: ReviewResult, *, retries_spent: int, policy: ReviewPolicy) -> ReviewVerdict:
    """The post-review verdict for a non-failed run.

    An empty proposal (a blank assessed diff) is never escalated to the owner: it
    is retried while Generation Retries remain and, once exhausted, reported as
    the existing tests already covering the request. A non-empty patch escalates
    when accepted or when the retries are exhausted, and is otherwise revised —
    exhaustion escalates or reports, it never fails the run (ADR-0004).
    """
    retry_available = retries_spent < policy.max_generation_retries
    if not review.diff.strip():
        return "revise" if retry_available else "already_covered"
    if not review.accepted and retry_available:
        return "revise"
    return "escalate"
