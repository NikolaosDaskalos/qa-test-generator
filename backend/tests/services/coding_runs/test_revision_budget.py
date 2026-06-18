from app.services.coding_runs.revision_budget import can_revise, is_revision_attempt, revision_attempts, spend_revision


def test_a_fresh_state_has_no_spent_attempts() -> None:
    assert revision_attempts({}) == 0
    assert is_revision_attempt({}) is False


def test_can_revise_while_under_the_limit() -> None:
    assert can_revise({}, limit=2) is True
    assert can_revise({"revision_attempts": 1}, limit=2) is True


def test_a_zero_limit_never_admits_a_revision() -> None:
    assert can_revise({}, limit=0) is False


def test_an_exhausted_budget_cannot_revise() -> None:
    assert can_revise({"revision_attempts": 2}, limit=2) is False


def test_spending_increments_the_count_for_a_state_update() -> None:
    assert spend_revision({}) == {"revision_attempts": 1}
    assert spend_revision({"revision_attempts": 1}) == {"revision_attempts": 2}


def test_a_spent_state_reads_as_a_revision_attempt() -> None:
    assert is_revision_attempt({"revision_attempts": 1}) is True
