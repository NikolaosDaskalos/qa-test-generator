from app.core import settings
from app.services.coding_runs.review_policy import ReviewPolicy


def test_review_policy_holds_an_explicit_threshold_and_retry_limit() -> None:
    policy = ReviewPolicy(pass_threshold=5, max_generation_retries=3)

    assert policy.pass_threshold == 5
    assert policy.max_generation_retries == 3


def test_from_settings_resolves_the_default_production_policy() -> None:
    policy = ReviewPolicy.from_settings()

    assert policy.pass_threshold == 7
    assert policy.max_generation_retries == 2
    assert policy.pass_threshold == settings.REVIEW_PASS_THRESHOLD
    assert policy.max_generation_retries == settings.MAX_GENERATION_RETRIES
