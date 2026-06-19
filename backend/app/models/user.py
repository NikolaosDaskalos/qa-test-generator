"""The ``User`` table: an authenticated account owning repositories and sessions."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.session import RepositorySession


class User(SQLModel, table=True):
    """An application account, holding the password hash and ownership relationships."""

    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore

    repository_sessions: list["RepositorySession"] = Relationship(back_populates="owner", sa_relationship_kwargs={"passive_deletes": "all"})
    repositories: list["Repository"] = Relationship(back_populates="user", cascade_delete=True)
