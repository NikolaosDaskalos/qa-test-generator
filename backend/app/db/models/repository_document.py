"""The persisted Repository Document mirrored by indexed Code Chunks."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.db.models.repository import Repository


class RepositoryDocumentMetadata(TypedDict):
    """Metadata stored with a Repository Document."""

    source: str
    file_path: str
    file_name: str
    file_type: str
    commit_sha: str
    branch: str


class RepositoryDocument(SQLModel, table=True):
    """The indexed representation of one file from a Repository."""

    __tablename__ = "repository_document"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    repository_id: uuid.UUID = Field(foreign_key="repository.id", nullable=False, index=True, ondelete="CASCADE")
    content: str = Field(sa_column=Column(Text, nullable=False))
    doc_metadata: RepositoryDocumentMetadata = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
    repository: "Repository" = Relationship(back_populates="repository_documents")
