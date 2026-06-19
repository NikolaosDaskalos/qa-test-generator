"""The planner's structured unit of work: a Research Intent.

A Research Intent names a piece of evidence the run needs to find, tagged to
target source code (what's implemented) or existing tests (what's already
tested). Candidate Repository paths are optional, untrusted hints — the backend
controls all actual evidence access and treats them only as retrieval seeds.
"""

from typing import Literal

from pydantic import BaseModel, Field

ResearchTarget = Literal["source", "test"]


class ResearchIntent(BaseModel):
    """One piece of evidence to find, tagged source vs. test."""

    target: ResearchTarget = Field(description="Kind of repository evidence to retrieve: source implementation code or existing test code.")
    description: str = Field(description="Natural-language query describing the exact evidence needed for the test-generation task.")
    candidate_paths: list[str] = Field(
        default_factory=list, description="Optional repository-relative path hints that may contain relevant evidence; omit unsafe or absolute paths."
    )
