"""Repository session tables: a conversation bound to one repository and its message history."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict, cast

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint, event, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper
from sqlalchemy.orm.state import InstanceState
from sqlmodel import Field, Relationship, SQLModel

from app.enums import SessionMessageRole

if TYPE_CHECKING:
    from app.db.models.coding_run import CodingRun
    from app.db.models.repository import Repository
    from app.db.models.user import User


NEW_SESSION_TITLE = "New session"
LEGACY_NEW_SESSION_TITLE = "New Repository Session"
MAX_DERIVED_SESSION_TITLE_LENGTH = 60


class CitationData(TypedDict):
    """A Repository source retained alongside a persisted assistant message."""

    source: str


class RepositorySession(SQLModel, table=True):
    """A conversation immutably bound to one Repository, owning its history and Coding Runs."""

    __tablename__ = "repository_session"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(default=NEW_SESSION_TITLE, min_length=1, max_length=255)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True, ondelete="CASCADE")
    repository_id: uuid.UUID = Field(foreign_key="repository.id", nullable=False, index=True, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )

    owner: "User" = Relationship(back_populates="repository_sessions")
    repository: "Repository" = Relationship(back_populates="sessions")
    history: list["SessionHistory"] = Relationship(back_populates="session", sa_relationship_kwargs={"passive_deletes": "all"})
    coding_runs: list["CodingRun"] = Relationship(back_populates="repository_session", sa_relationship_kwargs={"passive_deletes": "all"})


class SessionHistory(SQLModel, table=True):
    """One message in a session, ordered by ``position`` and carrying any source citations."""

    __tablename__ = "session_history"
    __table_args__ = (UniqueConstraint("session_id", "position", name="uq_session_history_position"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="repository_session.id", nullable=False, index=True, ondelete="CASCADE")
    role: SessionMessageRole
    content: str
    # JSONB on PostgreSQL; the JSON variant keeps the column portable to the SQLite engine used in persistence tests.
    citations: list[CitationData] = Field(
        default_factory=list, sa_column=Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, server_default=text("'[]'"))
    )
    position: int = Field(ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore

    session: RepositorySession = Relationship(back_populates="history")


@event.listens_for(RepositorySession, "before_update")
def _prevent_repository_reassignment(_mapper: Mapper[Any], _connection: Connection, target: RepositorySession) -> None:
    """Enforce the immutable repository binding by rejecting any update that changes ``repository_id``."""
    state = cast(InstanceState[RepositorySession], inspect(target))
    if state.attrs.repository_id.history.has_changes():
        raise ValueError("Repository Session binding is immutable")
