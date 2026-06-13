import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.enums.repository import RepositoryProvider, RepositoryStatus

if TYPE_CHECKING:
    from app.models import Branch, SourceDocument, User


class Repository(SQLModel, table=True):
    __tablename__ = "repository"
    __table_args__ = (UniqueConstraint("user_id", "repository_url", name="uq_user_id_repository_url"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=255, index=True)
    repository_url: str = Field(min_length=1, max_length=2048)
    provider: RepositoryProvider | None = Field(default=None, min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=255)
    default_branch: str | None = Field(default=None, max_length=255)
    indexed_commit_sha: str | None = Field(default=None, min_length=40, max_length=40)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True, ondelete="CASCADE")
    status: RepositoryStatus = Field(default=RepositoryStatus.pending, index=True)
    encrypted_token: str | None = Field(default=None, max_length=4096, nullable=True)
    token_expiration_date: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    local_path: str | None = Field(default=None, max_length=4096)
    failed_reason: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
    user: "User" = Relationship(back_populates="repositories")
    branches: list["Branch"] = Relationship(back_populates="repository", cascade_delete=True)
    source_documents: list["SourceDocument"] = Relationship(back_populates="repository", sa_relationship_kwargs={"passive_deletes": "all"})
