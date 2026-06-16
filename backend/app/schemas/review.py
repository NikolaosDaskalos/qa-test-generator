"""Structured Patch Review output: an accept/reject decision with findings.

Patch Review is evidence-based static assessment only — it never executes the
generated tests, installs dependencies, or implies runtime correctness. The
reviewer returns a decision and human-readable findings categorized by concern,
so the backend can persist them and the client can group them by category.
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
    """The reviewer's structured verdict: accepted or rejected, with findings."""

    accepted: bool = Field(description="Whether the Test Patch is accepted as-is.")
    findings: list[ReviewFinding] = Field(default_factory=list, description="Human-readable findings backing the decision.")
