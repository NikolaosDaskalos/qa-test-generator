import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.repository import Repository
    from app.models.search import SearchSession
    from app.models.todo import Todo


class User(SQLModel, table=True):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore

    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    todos: list["Todo"] = Relationship(back_populates="owner", cascade_delete=True)
    search_sessions: list["SearchSession"] = Relationship(back_populates="owner", cascade_delete=True)
    repositories: list["Repository"] = Relationship(back_populates="user", cascade_delete=True)
