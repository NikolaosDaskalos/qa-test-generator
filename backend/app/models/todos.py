import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

from app.models.users import User


# Base schema: shared Todo fields.
# This is reused by TodoCreate, TodoPublic, and the Todo DB model.
class TodoBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    completed: bool = Field(default=False)


# Database model: maps to the `todo` table.
# Includes persistence-related fields that should not be required from the client,
# such as `id`, `created_at`, and `owner_id`.
class Todo(TodoBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    created_at: datetime | None = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # Foreign key column: links each Todo row to one User row.
    # ondelete="CASCADE" asks the database to delete todos when the owner is deleted.
    owner_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        ondelete="CASCADE",
    )
    # ORM relationship: lets Python code access todo.owner instead of manually
    # querying the user table by owner_id.
    owner: User | None = Relationship(back_populates="todos")


# API schema: payload for creating a todo.
class TodoCreate(TodoBase):
    pass


# API schema: payload for updating a todo.
# Every field is optional to support partial updates.
class TodoUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore[assignment]
    description: str | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    completed: bool | None = Field(default=None)  # type: ignore[assignment]


# API response schema: public todo returned to the client.
class TodoPublic(TodoBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


# API response schema: standard list response for todos.
class TodosPublic(SQLModel):
    data: list[TodoPublic]
    count: int
