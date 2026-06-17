"""Structured Patch Review output: a score out of ten with findings.

Patch Review is evidence-based static assessment only — it never executes the
generated tests, installs dependencies, or implies runtime correctness. The
reviewer returns a quality ``score`` (0–10) and human-readable findings
categorized by concern; it no longer returns a pass/fail flag. The backend owns
the pass decision (``score`` against a configurable threshold), so the model
never gates the patch on its own.
"""

from typing import Literal

from pydantic import BaseModel, Field

# The concerns the reviewer assesses a Test Patch against.
FindingCategory = Literal["coverage", "readability", "conventions", "imports", "scope", "versioning"]


class ReviewFinding(BaseModel):
    """One categorized, human-readable observation about a proposed Test Patch."""

    category: FindingCategory = Field(description="The review concern this finding falls under.")
    detail: str = Field(description="A human-readable explanation of the finding.")


class PatchReview(BaseModel):
    """The reviewer's structured assessment: a quality score out of ten with findings."""

    score: int = Field(ge=0, le=10, description="The patch's overall quality out of ten; the backend decides pass/fail against a threshold.")
    findings: list[ReviewFinding] = Field(default_factory=list, description="Human-readable findings backing the score.")
