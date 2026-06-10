import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TodoBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    completed: bool = Field(default=False)


class TodoCreate(TodoBase):
    pass


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    completed: bool | None = Field(default=None)


class TodoPublic(TodoBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class TodosPublic(BaseModel):
    data: list[TodoPublic]
    count: int
