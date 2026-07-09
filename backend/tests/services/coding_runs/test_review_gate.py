import uuid

from app.schemas import ReviewResult
from app.services.coding_runs.review_gate import decide, generation_retries, is_generation_retry, spend_generation_retry
from app.services.coding_runs.review_policy import ReviewPolicy

POLICY = ReviewPolicy(pass_threshold=7, max_generation_retries=2)


def review(*, accepted: bool, score: int, diff: str = "diff --git a/tests/test_auth.py b/tests/test_auth.py\n+def test_x(): ...") -> ReviewResult:
    return ReviewResult(coding_run_id=uuid.uuid4(), accepted=accepted, score=score, threshold=POLICY.pass_threshold, findings=[], diff=diff)


def test_an_accepted_patch_escalates_to_the_owner() -> None:
    assert decide(review(accepted=True, score=9), retries_spent=0, policy=POLICY) == "escalate"


def test_a_below_threshold_patch_is_revised_while_generation_retries_remain() -> None:
    assert decide(review(accepted=False, score=4), retries_spent=1, policy=POLICY) == "revise"


def test_exhausted_generation_retries_escalate_the_below_threshold_patch() -> None:
    assert decide(review(accepted=False, score=4), retries_spent=2, policy=POLICY) == "escalate"


def test_a_zero_retry_budget_escalates_a_below_threshold_patch_without_revising() -> None:
    zero_budget = ReviewPolicy(pass_threshold=7, max_generation_retries=0)
    assert decide(review(accepted=False, score=4), retries_spent=0, policy=zero_budget) == "escalate"


def test_an_empty_proposal_is_revised_while_generation_retries_remain() -> None:
    assert decide(review(accepted=False, score=0, diff=""), retries_spent=0, policy=POLICY) == "revise"


def test_a_persistently_empty_proposal_is_reported_as_already_covered_never_escalated() -> None:
    assert decide(review(accepted=False, score=0, diff=""), retries_spent=2, policy=POLICY) == "already_covered"


def test_a_fresh_state_has_no_spent_generation_retries() -> None:
    assert generation_retries({}) == 0
    assert is_generation_retry({}) is False


def test_spending_increments_the_count_for_a_state_update() -> None:
    assert spend_generation_retry({}) == {"generation_retries": 1}
    assert spend_generation_retry({"generation_retries": 1}) == {"generation_retries": 2}


def test_a_spent_state_reads_as_a_generation_retry() -> None:
    assert is_generation_retry({"generation_retries": 1}) is True
