from app.agent.revision_attempt_budget import RevisionAttemptBudget


def test_fresh_budget_allows_one_revision_attempt() -> None:
    budget = RevisionAttemptBudget.fresh()

    assert budget.can_spend is True
    assert budget.is_revision_attempt is False


def test_spending_the_budget_marks_the_revision_attempt() -> None:
    spent = RevisionAttemptBudget.fresh().spend()

    assert spent.can_spend is False
    assert spent.is_revision_attempt is True
    assert spent.state_update() == {"revision_attempts": 1}


def test_exhausted_budget_produces_reviewing_failure() -> None:
    failure = RevisionAttemptBudget.fresh().spend().exhausted_failure()

    assert failure.failed_stage == "reviewing"
    assert "revision attempt" in failure.reason.lower()
