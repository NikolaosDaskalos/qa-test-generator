"""The configurable Revision Budget for a Test-Generation Task.

The budget owns the count of spent Revision Attempts and a configurable limit
(``MAX_REVISION_ATTEMPTS``). Exhausting it is not a failure: the post-review
``review_gate`` escalates the best below-threshold attempt to human review. The
budget therefore encodes only the spend/limit arithmetic, no terminal outcome.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.core.config import settings

REVISION_ATTEMPTS_STATE_KEY = "revision_attempts"


@dataclass(frozen=True)
class RevisionBudget:
    """Own the spent Revision Attempt count against a configurable limit."""

    spent: int = 0
    limit: int = 0

    @classmethod
    def fresh(cls, *, limit: int | None = None) -> RevisionBudget:
        return cls(spent=0, limit=_resolve_limit(limit))

    @classmethod
    def from_state(cls, state: Mapping[str, object], *, limit: int | None = None) -> RevisionBudget:
        return cls(spent=int(state.get(REVISION_ATTEMPTS_STATE_KEY) or 0), limit=_resolve_limit(limit))

    @property
    def can_spend(self) -> bool:
        return self.spent < self.limit

    @property
    def is_revision_attempt(self) -> bool:
        return self.spent > 0

    def spend(self) -> RevisionBudget:
        return RevisionBudget(spent=self.spent + 1, limit=self.limit)

    def state_update(self) -> dict[str, int]:
        return {REVISION_ATTEMPTS_STATE_KEY: self.spent}


def _resolve_limit(limit: int | None) -> int:
    return settings.MAX_REVISION_ATTEMPTS if limit is None else limit
