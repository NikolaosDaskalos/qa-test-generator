from sqlmodel import Field, SQLModel


# Generic API response schema for simple messages.
class Message(SQLModel):
    message: str


# API response schema: JSON payload returned after successful authentication.
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Internal/API schema: decoded JWT token contents.
# `sub` usually stores the subject/user identifier.
class TokenPayload(SQLModel):
    sub: str | None = None


# API schema: payload used when resetting a password with a token.
class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
