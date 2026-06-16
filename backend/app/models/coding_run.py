import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, DateTime, Text
from sqlmodel import Field, Relationship, SQLModel

from app.enums.coding_run import CodingRunStage, CodingRunStatus

if TYPE_CHECKING:
    from app.models.session import RepositorySession


class CodingRun(SQLModel, table=True):
    """A persisted Test-Generation Task: the durable domain record of one run.

    The graph checkpoint (keyed by ``thread_id``) holds in-flight state; this row
    is the record of truth for ownership, lifecycle state, failure, and the
    revision count later stages depend on. The owning Repository is reached
    through the Repository Session (immutably bound to one Repository), so it is
    not duplicated here.
    """

    __tablename__ = "coding_run"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    repository_session_id: uuid.UUID = Field(foreign_key="repository_session.id", nullable=False, index=True, ondelete="CASCADE")
    status: CodingRunStatus = Field(default=CodingRunStatus.queued, index=True)
    # The per-run LangGraph checkpointer thread id; resolves in-flight graph state back to this run.
    thread_id: str = Field(max_length=255, unique=True, index=True)
    failed_stage: CodingRunStage | None = Field(default=None)
    # A sanitized, user-safe explanation; never carries raw exception or model output.
    failure_reason: str | None = Field(default=None)
    revision_count: int = Field(default=0, ge=0)
    # The uniquely named, non-default temporary branch the Test Patch was built on.
    generation_branch: str | None = Field(default=None, max_length=255)
    # The canonical unified diff (Test Patch) derived by Git; the displayed record of truth.
    diff: str | None = Field(default=None, sa_column=Column(Text))
    # The complete generated file proposals ({path, content}) and the External References
    # consulted while writing them, kept separate from Repository Evidence.
    generated_files: list | None = Field(default=None, sa_column=Column(JSON))
    external_references: list | None = Field(default=None, sa_column=Column(JSON))
    # The Patch Review findings ({category, detail}) recorded for the latest review.
    review_findings: list | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )

    repository_session: "RepositorySession" = Relationship(back_populates="coding_runs")
