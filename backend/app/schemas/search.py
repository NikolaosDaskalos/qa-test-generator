import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchSessionBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(default="Untitles Search", max_length=255)


class SearchSessionCreate(SearchSessionBase):
    pass


class SearchSessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class SearchSessionPublic(SearchSessionBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SearchSessionsPublic(BaseModel):
    data: list[SearchSessionPublic]
    count: int


class SearchHistoryBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    result: str | None = None


class SearchHistoryCreate(SearchHistoryBase):
    session_id: uuid.UUID


class SearchHistoryPublic(SearchHistoryBase):
    id: uuid.UUID
    session_id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime


class SearchHistoriesPublic(BaseModel):
    data: list[SearchHistoryPublic]
    count: int


class AgentChatRequest(BaseModel):
    message: str


class AgentChatResponse(BaseModel):
    session_id: uuid.UUID
    reply: str
