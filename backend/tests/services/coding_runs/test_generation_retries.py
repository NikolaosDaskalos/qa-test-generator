import pytest

from app.services.coding_runs.generation_retries import can_retry_generation, generation_retries, is_generation_retry, spend_generation_retry


def test_a_fresh_state_has_no_spent_generation_retries() -> None:
    assert generation_retries({}) == 0
    assert is_generation_retry({}) is False


def test_can_retry_generation_while_under_the_limit() -> None:
    assert can_retry_generation({}, limit=2) is True
    assert can_retry_generation({"generation_retries": 1}, limit=2) is True


def test_zero_generation_retries_never_admits_a_retry() -> None:
    assert can_retry_generation({}, limit=0) is False


def test_exhausted_generation_retries_cannot_retry_generation() -> None:
    assert can_retry_generation({"generation_retries": 2}, limit=2) is False


def test_spending_increments_the_count_for_a_state_update() -> None:
    assert spend_generation_retry({}) == {"generation_retries": 1}
    assert spend_generation_retry({"generation_retries": 1}) == {"generation_retries": 2}


def test_a_spent_state_reads_as_a_generation_retry() -> None:
    assert is_generation_retry({"generation_retries": 1}) is True


def test_can_retry_generation_requires_an_explicit_limit() -> None:
    # The limit is resolved once at composition; the helper never falls back to
    # global settings when it is omitted.
    with pytest.raises(TypeError):
        can_retry_generation({})  # type: ignore[call-arg]
