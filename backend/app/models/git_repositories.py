import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import get_datetime_utc

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.users import User


class GitRepositoryProvider(str, Enum):
    github = "github"
    gitlab = "gitlab"
    bitbucket = "bitbucket"
    other = "other"


class GitRepositoryStatus(str, Enum):
    pending = "pending"
    cloning = "cloning"
    ready = "ready"
    failed = "failed"
    archived = "archived"


# Shared fields used by GitRepository create/public schemas and the DB model.
class GitRepositoryBase(SQLModel):
    name: str = Field(min_length=1, max_length=255, index=True)
    repository_url: str = Field(min_length=1, max_length=255)
    provider: GitRepositoryProvider = GitRepositoryProvider.other
    repository_owner: str = Field(min_length=1, max_length=255)
    default_branch: str | None = Field(default=None, max_length=255)


# Plain credentials are accepted only by request schemas.
class GitRepositoryCreate(SQLModel):
    repository_url: str = Field(min_length=1, max_length=255)
    token: str | None = Field(default=None, min_length=1, max_length=255)
    token_expiration_days: int


class GitRepository(GitRepositoryBase, table=True):
    __tablename__ = "git_repository"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "repository_url",
            name="uq_repository_owner_url",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    status: GitRepositoryStatus = Field(
        default=GitRepositoryStatus.pending,
        index=True,
    )
    hashed_token: str | None = Field(default=None, nullable=True)
    token_expiration_date: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    # Useful for a single-worker deployment. For multiple workers, move local
    # clone state into a separate checkout table keyed by worker/host.
    local_path: str | None = Field(default=None, max_length=255)
    last_cloned_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    last_error: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": get_datetime_utc},
    )

    user: "User" = Relationship(back_populates="repositories")
    branches: list["Branch"] = Relationship(
        back_populates="git_repository",
        cascade_delete=True,
    )


class GitRepositoryPublic(GitRepositoryBase):
    id: uuid.UUID
    user_id: uuid.UUID
    status: GitRepositoryStatus
    last_cloned_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class GitRepositoriesPublic(SQLModel):
    data: list[GitRepositoryPublic]
    count: int
