"""Test AI Cost estimation from token usage and the local price table (ADR-0013)."""

import pytest

from app.services.usage.pricing import price_for


def test_price_for_computes_gpt_4o_mini_cost() -> None:
    """A known model prices as input_tokens x input_rate + output_tokens x output_rate."""
    cost = price_for("gpt-4o-mini", 1000, 500)
    assert cost == pytest.approx(0.15 * 1000 / 1_000_000 + 0.60 * 500 / 1_000_000)


@pytest.mark.parametrize(
    ("model", "input_rate", "output_rate"),
    [
        ("gpt-4o", 2.50, 10.00),
        ("gpt-4o-mini", 0.15, 0.60),
        ("claude-haiku-4-5", 1.00, 5.00),
        ("claude-sonnet-4-6", 3.00, 15.00),
    ],
)
def test_price_for_prices_every_configured_model(model, input_rate, output_rate) -> None:
    """Each of the four configured chat models resolves to its own rate."""
    cost = price_for(model, 2000, 1000)
    assert cost == pytest.approx(2000 * input_rate / 1_000_000 + 1000 * output_rate / 1_000_000)


def test_price_for_resolves_a_dated_response_id_by_longest_prefix() -> None:
    """A provider date suffix resolves to the base key, and to the longer key over its prefix."""
    dated = price_for("gpt-4o-mini-2024-07-18", 1000, 500)
    assert dated == price_for("gpt-4o-mini", 1000, 500)
    # The shorter 'gpt-4o' key is also a prefix, but the longest match must win.
    assert dated != price_for("gpt-4o", 1000, 500)


def test_price_for_returns_none_and_warns_for_an_unknown_model(caplog) -> None:
    """An id missing from the table records cost=None and emits a loud WARNING, never a substitute rate."""
    with caplog.at_level("WARNING"):
        cost = price_for("mystery-model-1", 1000, 500)
    assert cost is None
    assert any("mystery-model-1" in record.message for record in caplog.records)
