"""Estimate AI Cost from token usage and a local per-model price table (ADR-0013).

Cost is *derived*, never provider-reported: the providers used return token counts
only, so ``cost = input_tokens x input_rate + output_tokens x output_rate`` with rates
maintained locally. Every cost computation goes through :func:`price_for`, so swapping
the local table for a maintained pricing library later is a one-module change.
"""

import logging

logger = logging.getLogger(__name__)

# USD per 1M tokens, (input_rate, output_rate). The four chat models configured today
# (ADR-0010 tiers and their cross-provider fallbacks). A repriced or new model is a
# change here; until then its calls record cost = None with a loud WARNING.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}

_PER_MILLION = 1_000_000


def price_for(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return the derived USD cost for one LLM call, or ``None`` for an unpriced model.

    The rate is keyed off the model the *response* reports (ADR-0010 fallback), which may
    carry a provider date suffix (``gpt-4o-mini-2024-07-18``); the longest table key that
    is a prefix of that id wins, so ``gpt-4o-mini-...`` resolves to ``gpt-4o-mini`` and not
    the shorter ``gpt-4o``. An id matching no key records ``None`` and logs a WARNING rather
    than silently substituting another model's rate (a ~20x error hidden behind a number).
    """
    rates = _rates_for(model)
    if rates is None:
        logger.warning("No price table entry for model=%s; recording cost=None", model)
        return None
    input_rate, output_rate = rates
    return input_tokens * input_rate / _PER_MILLION + output_tokens * output_rate / _PER_MILLION


def _rates_for(model: str) -> tuple[float, float] | None:
    """Resolve a reported model id to its rates by longest-prefix match on the table."""
    candidates = [key for key in PRICE_TABLE if model == key or model.startswith(key)]
    if not candidates:
        return None
    return PRICE_TABLE[max(candidates, key=len)]
