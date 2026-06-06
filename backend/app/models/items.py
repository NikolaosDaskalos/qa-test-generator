import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import get_datetime_utc
from app.models.users import User


# Base schema: fields common to items in create/update/public contexts.
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# API schema: payload for creating an item.
class ItemCreate(ItemBase):
    pass


# API schema: payload for updating an item.
# `title` becomes optional so clients can update only part of the item.
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore[assignment]


# Database model: maps to the `item` table.
# Contains DB-specific fields such as primary key, timestamp, foreign key,
# and relationship back to the owning user.
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# API response schema: public item returned to clients.
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


# API response schema: standard list response for items.
class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int
