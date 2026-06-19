"""Request/response schemas for the repository API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enums.repository import RepositoryProvider, RepositoryStatus


class RepositoryUpdate(BaseModel):
    """Update payload supplying a new access token and optional expiry."""

    token: str = Field(min_length=1, max_length=2048)
    token_expiration_days: int | None = Field(default=None, gt=0)


class RepositoryCreate(RepositoryUpdate):
    """Registration payload: a repository URL plus its access token."""

    repository_url: str = Field(min_length=1, max_length=2048)


class RepositoryPublic(BaseModel):
    """A repository as exposed to clients, without the stored token."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    repository_url: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=255)
    provider: RepositoryProvider | None = Field(default=None, min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=255)
    default_branch: str | None = Field(default=None, max_length=255)
    indexed_commit_sha: str | None = Field(default=None, min_length=40, max_length=40)
    status: RepositoryStatus
    failed_reason: str | None
    created_at: datetime
    updated_at: datetime


class RepositoriesPublic(BaseModel):
    """A page of repositories with the total count."""

    data: list[RepositoryPublic]
    count: int
