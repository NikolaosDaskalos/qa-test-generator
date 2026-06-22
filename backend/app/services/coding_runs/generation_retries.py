"""Utility functions over the Generation Retries held in graph state.

The spent Generation Retry count lives in graph state under ``generation_retries``;
the limit is the configurable ``MAX_GENERATION_RETRIES``. Exhausting the retries is
not a failure: the post-review router escalates the best below-threshold attempt to
human review. These helpers encode only the spend/limit arithmetic over that one
count — no terminal outcome and no storage of their own.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core import settings

GENERATION_RETRIES_STATE_KEY = "generation_retries"


def generation_retries(state: Mapping[str, object]) -> int:
    """The number of Generation Retries already spent, read from graph state."""
    return int(state.get(GENERATION_RETRIES_STATE_KEY) or 0)


def is_generation_retry(state: Mapping[str, object]) -> bool:
    """Whether at least one Generation Retry has been spent."""
    return generation_retries(state) > 0


def can_retry_generation(state: Mapping[str, object], *, limit: int | None = None) -> bool:
    """Whether the policy admits one more Generation Retry against its limit."""
    return generation_retries(state) < _resolve_limit(limit)


def spend_generation_retry(state: Mapping[str, object]) -> dict[str, int]:
    """Graph-state update that records one more spent Generation Retry."""
    return {GENERATION_RETRIES_STATE_KEY: generation_retries(state) + 1}


def _resolve_limit(limit: int | None) -> int:
    """Return the explicit limit, falling back to the configured ``MAX_GENERATION_RETRIES``."""
    return settings.MAX_GENERATION_RETRIES if limit is None else limit
