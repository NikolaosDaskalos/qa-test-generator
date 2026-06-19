"""Utility functions over the Revision Budget held in graph state.

The spent Revision Attempt count lives in graph state under ``revision_attempts``;
the limit is the configurable ``MAX_REVISION_ATTEMPTS``. Exhausting the budget is
not a failure: the post-review router escalates the best below-threshold attempt to
human review. These helpers encode only the spend/limit arithmetic over that one
count — no terminal outcome and no storage of their own.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core import settings

REVISION_ATTEMPTS_STATE_KEY = "revision_attempts"


def revision_attempts(state: Mapping[str, object]) -> int:
    """The number of Revision Attempts already spent, read from graph state."""
    return int(state.get(REVISION_ATTEMPTS_STATE_KEY) or 0)


def is_revision_attempt(state: Mapping[str, object]) -> bool:
    """Whether at least one Revision Attempt has been spent."""
    return revision_attempts(state) > 0


def can_revise(state: Mapping[str, object], *, limit: int | None = None) -> bool:
    """Whether the budget admits one more Revision Attempt against its limit."""
    return revision_attempts(state) < _resolve_limit(limit)


def spend_revision(state: Mapping[str, object]) -> dict[str, int]:
    """Graph-state update that records one more spent Revision Attempt."""
    return {REVISION_ATTEMPTS_STATE_KEY: revision_attempts(state) + 1}


def _resolve_limit(limit: int | None) -> int:
    """Return the explicit limit, falling back to the configured ``MAX_REVISION_ATTEMPTS``."""
    return settings.MAX_REVISION_ATTEMPTS if limit is None else limit
