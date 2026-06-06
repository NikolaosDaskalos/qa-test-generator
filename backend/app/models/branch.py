import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.git_repositories import GitRepository


class BranchBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)


class BranchCreate(BranchBase):
    pass


class Branch(BranchBase, table=True):
    __tablename__ = "branch"
    __table_args__ = (
        UniqueConstraint(
            "git_repository_id",
            "name",
            name="uq_git_repository_branch_name",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    git_repository_id: uuid.UUID = Field(
        foreign_key="git_repository.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    # local_head_sha: SHA currently checked out in the local clone.
    local_head_sha: str = Field(nullable=False, max_length=64)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
    git_repository: "GitRepository" = Relationship(back_populates="branches")
