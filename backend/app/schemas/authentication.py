"""Authentication wire schemas: tokens, JWT payload, and password-reset requests."""

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A simple ``{"message": ...}`` response body."""

    message: str


class Token(BaseModel):
    """An OAuth2 access-token response."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """The decoded JWT payload; ``sub`` is the user id."""

    sub: str | None = None


class NewPassword(BaseModel):
    """A password-reset submission pairing the reset token with the new password."""

    token: str
    new_password: str = Field(min_length=8, max_length=128)
