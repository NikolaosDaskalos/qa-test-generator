"""User wire schemas for admin management, self-service, and public reads."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Shared user fields common to creation, update, and public reads."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


class UserCreate(UserBase):
    """Admin payload to create a user with a plaintext password."""

    password: str = Field(min_length=8, max_length=128)


class UserRegister(BaseModel):
    """Self-service signup payload."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserUpdate(UserBase):
    """Admin payload to update a user; all fields optional."""

    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(BaseModel):
    """Self-service update of one's own name and email."""

    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(BaseModel):
    """Self-service password change, verifying the current password."""

    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserPublic(UserBase):
    """A user as exposed to clients, without the password hash."""

    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(BaseModel):
    """A page of users with the total count."""

    data: list[UserPublic]
    count: int
