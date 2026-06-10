import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.items import Item
    from app.models.repository import Repository
    from app.models.searches import SearchSession
    from app.models.todos import Todo


# Base schema: shared user fields used by API schemas and the DB model.
# This is not a DB table because it does not use `table=True`.
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# API schema: data received when an admin/system creates a user.
# It extends UserBase and adds the plain password received from the client.
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


# API schema: data received when a user registers.
# It is separated from UserCreate so registration can expose only the fields
# that a normal user is allowed to submit.
class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# API schema: data received when updating a user.
# All fields are optional because PATCH/partial-update endpoints should allow
# the client to send only the fields that need to change.
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


# API schema: fields a logged-in user can update for their own account.
class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


# API schema: payload used for changing an existing password.
class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model: this class maps to the `user` table because of `table=True`.
# It contains database-only fields such as `id`, `hashed_password`, timestamps,
# and ORM relationships. Notice that we store `hashed_password`, not the plain
# password received by UserCreate/UserRegister
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    # ORM relationships: these are not plain API fields.
    # They connect this user with the related rows in other tables.
    # `cascade_delete=True` means related records are deleted when the user is deleted.
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    todos: list["Todo"] = Relationship(back_populates="owner", cascade_delete=True)
    search_sessions: list["SearchSession"] = Relationship(back_populates="owner", cascade_delete=True)
    repositories: list["Repository"] = Relationship(back_populates="user", cascade_delete=True)


# API response schema: public representation of a user.
# It intentionally excludes sensitive/internal fields such as `hashed_password`.
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


# API response schema: standard list response for users.
class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int
