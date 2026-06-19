"""Request/response schemas for the repository session API and its streaming turns."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import CodingRunStage, CodingRunStatus, SessionMessageRole
from app.models import NEW_SESSION_TITLE
from app.schemas.agent_stream import REVIEW_DISCLAIMER, Citation
from app.schemas.generation import ExternalReference, GeneratedFile
from app.schemas.review import ReviewFinding


class RepositorySessionCreate(BaseModel):
    """Payload to open a session bound to a repository."""

    repository_id: uuid.UUID
    title: str = Field(default=NEW_SESSION_TITLE, min_length=1, max_length=255)


class HumanDecisionRequest(BaseModel):
    """The owner's human-in-the-loop decision on a reviewed Test Patch.

    Delivered through the same session stream that produced the patch: it resumes
    the suspended Coding Run rather than starting a new one. ``approved`` is the
    verdict; a rejection discards the patch.
    """

    coding_run_id: uuid.UUID
    approved: bool
    feedback: str = Field(default="", max_length=4000)


class RepositoryQuestionRequest(BaseModel):
    """One turn on a session stream: a new question or a decision resuming a paused run.

    The same entry point both asks a repository-grounded/test-generation question and
    delivers the owner's human-in-the-loop decision, so exactly one of ``question`` or
    ``decision`` must be present — never both, never neither.
    """

    question: str | None = Field(default=None, max_length=4000)
    decision: HumanDecisionRequest | None = None

    @model_validator(mode="after")
    def _exactly_one_intent(self) -> "RepositoryQuestionRequest":
        """Require exactly one of ``question`` or ``decision``, and a non-blank question."""
        if (self.question is None) == (self.decision is None):
            raise ValueError("Provide either a question or a decision, not both")
        if self.question is not None and not self.question.strip():
            raise ValueError("question must not be empty")
        return self


class RepositorySessionPublic(BaseModel):
    """A session as exposed to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    repository_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RepositorySessionsPublic(BaseModel):
    """A page of sessions with the total count."""

    data: list[RepositorySessionPublic]
    count: int


class SessionHistoryPublic(BaseModel):
    """One persisted session message as exposed to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: SessionMessageRole
    content: str
    citations: list[Citation]
    position: int
    created_at: datetime


class SessionHistoriesPublic(BaseModel):
    """A session's full message history."""

    data: list[SessionHistoryPublic]


class CodingRunPublic(BaseModel):
    """Post-stream read of a Coding Run's persisted lifecycle, review, and failure state.

    ``disclaimer`` restates that the generated tests were not executed and their
    runtime correctness was not verified — the Patch Review was static only.
    """

    id: uuid.UUID
    status: CodingRunStatus
    failed_stage: CodingRunStage | None = None
    failure_reason: str | None = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    diff: str | None = None
    disclaimer: str = REVIEW_DISCLAIMER


class RunPatchPublic(BaseModel):
    """Post-stream read of a Coding Run's persisted Test Patch content."""

    coding_run_id: uuid.UUID
    diff: str
    generated_files: list[GeneratedFile] = Field(default_factory=list)
    external_references: list[ExternalReference] = Field(default_factory=list)
