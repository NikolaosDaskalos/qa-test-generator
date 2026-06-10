import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.users import User


class RepositoryProvider(str, Enum):
    github = "github"
    gitlab = "gitlab"
    bitbucket = "bitbucket"


class RepositoryStatus(str, Enum):
    pending = "pending"
    cloning = "cloning"
    cloned = "cloned"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


# Shared fields used by Repository create/public schemas and the DB model.
class RepositoryBase(SQLModel):
    name: str = Field(min_length=1, max_length=255, index=True)
    repository_url: str = Field(min_length=1, max_length=2048)
    provider: RepositoryProvider | None = Field(default=None, min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=255)
    default_branch: str | None = Field(default=None, max_length=255)


# Plain credentials are accepted only by request schemas.
class RepositoryUpdate(SQLModel):
    """Accept the only mutable repository credential fields."""

    token: str = Field(min_length=1, max_length=2048)
    token_expiration_days: int | None = Field(default=None, gt=0)


# Plain credentials are accepted only by request schemas.
class RepositoryCreate(RepositoryUpdate):
    """Accept data required to register a repository."""

    repository_url: str = Field(min_length=1, max_length=2048)


class Repository(RepositoryBase, table=True):
    __tablename__ = "repository"
    __table_args__ = (UniqueConstraint("user_id", "repository_url", name="uq_user_id_repository_url"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True, ondelete="CASCADE")
    status: RepositoryStatus = Field(default=RepositoryStatus.pending, index=True)
    encrypted_token: str | None = Field(default=None, max_length=4096, nullable=True)
    token_expiration_date: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    # Useful for a single-worker deployment. For multiple workers, move local
    # clone state into a separate checkout table keyed by worker/host.
    local_path: str | None = Field(default=None, max_length=4096)
    failed_reason: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )

    user: "User" = Relationship(back_populates="repositories")
    branches: list["Branch"] = Relationship(back_populates="repository", cascade_delete=True)


class RepositoryPublic(RepositoryBase):
    id: uuid.UUID
    user_id: uuid.UUID
    status: RepositoryStatus
    failed_reason: str | None
    created_at: datetime
    updated_at: datetime


class RepositoriesPublic(SQLModel):
    data: list[RepositoryPublic]
    count: int
