import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enums.repository import RepositoryProvider, RepositoryStatus


class RepositoryBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=1, max_length=255)
    repository_url: str = Field(min_length=1, max_length=2048)
    provider: RepositoryProvider | None = Field(default=None, min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=255)
    default_branch: str | None = Field(default=None, max_length=255)


class RepositoryUpdate(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    token_expiration_days: int | None = Field(default=None, gt=0)


class RepositoryCreate(RepositoryUpdate):
    repository_url: str = Field(min_length=1, max_length=2048)


class RepositoryPublic(RepositoryBase):
    id: uuid.UUID
    user_id: uuid.UUID
    status: RepositoryStatus
    failed_reason: str | None
    created_at: datetime
    updated_at: datetime


class RepositoriesPublic(BaseModel):
    data: list[RepositoryPublic]
    count: int
