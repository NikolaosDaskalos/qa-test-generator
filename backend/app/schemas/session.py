"""Request/response schemas for the repository session API and its streaming turns."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import NEW_SESSION_TITLE
from app.enums import CodingRunStage, CodingRunStatus, OwnerVerdict, SessionMessageRole
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
    the suspended Coding Run rather than starting a new one. ``verdict`` is the
    three-way Owner Decision — a rejection discards the patch, an approval commits
    and opens a Pull Request, and an Edit returns the run to generation to revise
    the Test Files in place against ``feedback``. Feedback is required (non-empty)
    for an Edit — it is the only thing steering the revision — optional for a
    rejection, and ignored for an approval.
    """

    coding_run_id: uuid.UUID
    verdict: OwnerVerdict
    feedback: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def _edit_requires_feedback(self) -> "HumanDecisionRequest":
        """Reject an Edit with blank/missing feedback at the schema boundary."""
        if self.verdict is OwnerVerdict.edit and not self.feedback.strip():
            raise ValueError("feedback is required for an edit verdict")
        return self


class RepositoryQuestionRequest(BaseModel):
    """One turn on a session stream: a new question or a decision resuming a paused run.

    The same entry point both asks a repository-grounded/code-generation question and
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
    user_id: uuid.UUID
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
    # The Coding Run this message belongs to, when the turn was a code-generation run; the client rebuilds the card from the durable run.
    coding_run_id: uuid.UUID | None = None
    created_at: datetime


class SessionHistoriesPublic(BaseModel):
    """One page of a session's complete history, ordered chronologically, with upward-pagination info.

    ``next_before`` is the position cursor the client passes back as ``before`` to fetch the next older
    page; it is ``None`` once ``has_more`` is false and the beginning of history has been reached.
    """

    data: list[SessionHistoryPublic]
    has_more: bool = False
    next_before: int | None = None


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
    # The URL of the Pull Request opened on Approval, restored so the approved card links to it after a reload.
    pull_request_url: str | None = None
    disclaimer: str = REVIEW_DISCLAIMER


class RunPatchPublic(BaseModel):
    """Post-stream read of a Coding Run's persisted Test Patch content."""

    coding_run_id: uuid.UUID
    diff: str
    generated_files: list[GeneratedFile] = Field(default_factory=list)
    external_references: list[ExternalReference] = Field(default_factory=list)


class TurnCostPublic(BaseModel):
    """The AI Cost of a single turn, summed from its Usage Records (ADR-0014).

    Keyed by the anchor the terminal event hands the client — the assistant
    ``session_history_id`` of a Repository question's ``Result``, or the ``coding_run_id``
    of a Code Generation Task — so the cost can be shown the moment a turn finishes and
    again on reload, off the closed Agent Stream. Exactly one anchor is set; the response
    echoes back whichever keyed the read. ``cost`` sums the priced calls (an unpriced model
    contributes tokens but no cost); a turn with no recorded usage reads back as a
    well-defined zero, never an error.
    """

    session_history_id: uuid.UUID | None = None
    coding_run_id: uuid.UUID | None = None
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
