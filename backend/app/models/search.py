import uuid
from datetime import UTC, datetime

from sqlmodel import Field, Relationship, SQLModel

from app.models.user import User


class SearchSession(SQLModel, table=True):
    __tablename__ = "search_session"

    title: str = Field(default="Untitles Search", max_length=255)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    memory: str = Field(default="[]")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    owner: User = Relationship(back_populates="search_sessions")
    history: list["SearchHistory"] = Relationship(back_populates="session", cascade_delete=True)


class SearchHistory(SQLModel, table=True):
    __tablename__ = "search_history"

    query: str
    result: str | None = None
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="search_session.id", nullable=False, ondelete="CASCADE")
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    session: SearchSession = Relationship(back_populates="history")
    owner: User = Relationship()
