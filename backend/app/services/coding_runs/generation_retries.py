"""Utility functions over the Generation Retries held in graph state.

The spent Generation Retry count lives in graph state under ``generation_retries``;
the limit is the resolved ``ReviewPolicy.max_generation_retries``. Exhausting the retries is
not a failure: the post-review router escalates the best below-threshold attempt to
human review. These helpers encode only the spend/limit arithmetic over that one
count — no terminal outcome and no storage of their own.
"""

from __future__ import annotations

from collections.abc import Mapping

GENERATION_RETRIES_STATE_KEY = "generation_retries"


def generation_retries(state: Mapping[str, object]) -> int:
    """The number of Generation Retries already spent, read from graph state."""
    return int(state.get(GENERATION_RETRIES_STATE_KEY) or 0)


def is_generation_retry(state: Mapping[str, object]) -> bool:
    """Whether at least one Generation Retry has been spent."""
    return generation_retries(state) > 0


def can_retry_generation(state: Mapping[str, object], *, limit: int) -> bool:
    """Whether the policy admits one more Generation Retry against its limit.

    The ``limit`` is the resolved ``ReviewPolicy.max_generation_retries`` threaded
    from composition; this helper never reads global settings on its own.
    """
    return generation_retries(state) < limit


def spend_generation_retry(state: Mapping[str, object]) -> dict[str, int]:
    """Graph-state update that records one more spent Generation Retry."""
    return {GENERATION_RETRIES_STATE_KEY: generation_retries(state) + 1}
