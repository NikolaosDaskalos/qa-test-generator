"""The single-attempt budget for a Revision Attempt."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.schemas.agent_stream import RunFailure

REVISION_ATTEMPT_LIMIT = 1
REVISION_ATTEMPTS_STATE_KEY = "revision_attempts"
SECOND_REVIEW_REJECTED = "The reviewer rejected the revised tests after one revision attempt."


@dataclass(frozen=True)
class RevisionAttemptBudget:
    """Own the Revision Attempt count and exhausted-review failure."""

    spent: int = 0

    @classmethod
    def fresh(cls) -> RevisionAttemptBudget:
        return cls()

    @classmethod
    def from_state(cls, state: Mapping[str, object]) -> RevisionAttemptBudget:
        return cls(spent=int(state.get(REVISION_ATTEMPTS_STATE_KEY) or 0))

    @property
    def can_spend(self) -> bool:
        return self.spent < REVISION_ATTEMPT_LIMIT

    @property
    def is_revision_attempt(self) -> bool:
        return self.spent > 0

    def spend(self) -> RevisionAttemptBudget:
        return RevisionAttemptBudget(spent=min(self.spent + 1, REVISION_ATTEMPT_LIMIT))

    def state_update(self) -> dict[str, int]:
        return {REVISION_ATTEMPTS_STATE_KEY: self.spent}

    def exhausted_failure(self) -> RunFailure:
        return RunFailure(failed_stage="reviewing", reason=SECOND_REVIEW_REJECTED)
