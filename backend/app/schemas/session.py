import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enums.coding_run import CodingRunStage, CodingRunStatus
from app.enums.session import SessionMessageRole
from app.schemas.agent_stream import REVIEW_DISCLAIMER, Citation
from app.schemas.generation import ExternalReference, GeneratedFile
from app.schemas.review import ReviewFinding


class RepositorySessionCreate(BaseModel):
    repository_id: uuid.UUID
    title: str = Field(default="New Repository Session", min_length=1, max_length=255)


class RepositoryQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class RepositorySessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    repository_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SessionHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: SessionMessageRole
    content: str
    citations: list[Citation]
    position: int
    created_at: datetime


class SessionHistoriesPublic(BaseModel):
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
