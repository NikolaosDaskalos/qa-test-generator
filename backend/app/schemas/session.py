import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enums.session import SessionMessageRole


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
    position: int
    created_at: datetime


class SessionHistoriesPublic(BaseModel):
    data: list[SessionHistoryPublic]
