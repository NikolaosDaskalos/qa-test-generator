from app.services.coding_runs.revision_budget import RevisionBudget


def test_fresh_budget_can_spend_up_to_its_limit() -> None:
    budget = RevisionBudget.fresh(limit=2)

    assert budget.can_spend is True
    assert budget.is_revision_attempt is False


def test_a_zero_limit_budget_can_never_spend() -> None:
    budget = RevisionBudget.fresh(limit=0)

    assert budget.can_spend is False
    assert budget.is_revision_attempt is False


def test_spending_marks_a_revision_attempt_and_serializes_the_count() -> None:
    spent = RevisionBudget.fresh(limit=2).spend()

    assert spent.is_revision_attempt is True
    assert spent.can_spend is True  # one of two attempts spent, budget remains
    assert spent.state_update() == {"revision_attempts": 1}


def test_budget_is_exhausted_once_the_limit_is_reached() -> None:
    exhausted = RevisionBudget.fresh(limit=2).spend().spend()

    assert exhausted.can_spend is False
    assert exhausted.is_revision_attempt is True
    assert exhausted.state_update() == {"revision_attempts": 2}


def test_from_state_reads_the_spent_count_against_a_given_limit() -> None:
    budget = RevisionBudget.from_state({"revision_attempts": 1}, limit=1)

    assert budget.is_revision_attempt is True
    assert budget.can_spend is False
