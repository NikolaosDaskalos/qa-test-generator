"""Specify the owner's three-way Owner Decision contract at the schema boundary."""

import uuid

import pytest
from pydantic import ValidationError

from app.enums import OwnerVerdict
from app.schemas import HumanDecisionRequest


def test_edit_verdict_requires_non_empty_feedback() -> None:
    """An Edit steers the model with words, so blank/missing feedback is rejected at the boundary."""
    with pytest.raises(ValidationError):
        HumanDecisionRequest(coding_run_id=uuid.uuid4(), verdict=OwnerVerdict.edit, feedback="   ")
    with pytest.raises(ValidationError):
        HumanDecisionRequest(coding_run_id=uuid.uuid4(), verdict=OwnerVerdict.edit)


def test_edit_verdict_accepts_non_empty_feedback() -> None:
    """An Edit with a real note is a valid decision the model can revise against."""
    decision = HumanDecisionRequest(coding_run_id=uuid.uuid4(), verdict=OwnerVerdict.edit, feedback="cover the unhappy path too")

    assert decision.verdict is OwnerVerdict.edit
    assert decision.feedback == "cover the unhappy path too"


def test_reject_and_approve_do_not_require_feedback() -> None:
    """Feedback is optional for a rejection and ignored for an approval — only Edit needs words."""
    reject = HumanDecisionRequest(coding_run_id=uuid.uuid4(), verdict=OwnerVerdict.reject)
    approve = HumanDecisionRequest(coding_run_id=uuid.uuid4(), verdict=OwnerVerdict.approve)

    assert reject.verdict is OwnerVerdict.reject
    assert approve.verdict is OwnerVerdict.approve
