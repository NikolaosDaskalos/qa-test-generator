import uuid
from datetime import UTC, datetime

from sqlmodel import Field, Relationship, SQLModel

from app.models.users import User


# Base schema: common fields for a search session.
class SearchSessionBase(SQLModel):
    title: str = Field(default="Untitles Search", max_length=255)


# Database model: maps to the `search_session` table.
# Represents one conversation/session of the searching agent for a specific user.
class SearchSession(SearchSessionBase, table=True):
    __tablename__ = "search_session"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    # Stored as JSON text, for example:
    # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    # It keeps the conversational memory/context for this search session.
    memory: str = Field(default="[]")

    # Timestamps for session lifecycle.
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ORM relationships.
    # owner: the User that owns the session.
    # history: all SearchHistory rows belonging to this session.
    owner: User = Relationship(back_populates="search_sessions")
    history: list["SearchHistory"] = Relationship(
        back_populates="session", cascade_delete=True
    )


# API schema: payload for creating a new search session.
class SearchSessionCreate(SearchSessionBase):
    pass


# API schema: payload for updating a search session.
# Only title is editable here, and it is optional for partial update endpoints.
class SearchSessionUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=255)


# API response schema: public search session returned to the client.
class SearchSessionPublic(SearchSessionBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# API response schema: standard list response for search sessions.
class SearchSessionsPublic(SQLModel):
    data: list[SearchSessionPublic]
    count: int


# -----------------------------------------------------------------------------
# Search history schemas and model
# -----------------------------------------------------------------------------


# Base schema: shared fields for a single search/answer entry.
class SearchHistoryBase(SQLModel):
    query: str
    result: str | None = None  # Agent answer. None means no result has been stored yet.


# Database model: maps to the `search_history` table.
# Represents one user query and the corresponding agent result inside a session.
class SearchHistory(SearchHistoryBase, table=True):
    __tablename__ = "search_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Foreign key to the session where this query belongs.
    session_id: uuid.UUID = Field(
        foreign_key="search_session.id", nullable=False, ondelete="CASCADE"
    )
    # Foreign key to the user who made the query.
    # Keeping owner_id here makes it easier to filter a user's history directly.
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ORM relationships for navigation in Python code.
    session: SearchSession = Relationship(back_populates="history")
    owner: User = Relationship()


# API schema: payload for creating a search history entry.
# The client/API layer must specify which session the query belongs to.
class SearchHistoryCreate(SearchHistoryBase):
    session_id: uuid.UUID


# API response schema: public search history entry returned to the client.
class SearchHistoryPublic(SearchHistoryBase):
    id: uuid.UUID
    session_id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime


# API response schema: standard list response for search history entries.
class SearchHistoriesPublic(SQLModel):
    data: list[SearchHistoryPublic]
    count: int


# -----------------------------------------------------------------------------
# Agent chat API schemas
# -----------------------------------------------------------------------------


# API request schema: message sent by the client to the agentic chat endpoint.
class AgentChatRequest(SQLModel):
    message: str


# API response schema: answer returned by the agentic chat endpoint.
class AgentChatResponse(SQLModel):
    session_id: uuid.UUID
    reply: str
