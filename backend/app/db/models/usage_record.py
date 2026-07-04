"""The ``UsageRecord`` table: one durable row per LLM call for AI Cost (ADR-0013)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class UsageRecord(SQLModel, table=True):
    """The metered usage and attribution of a single LLM call.

    Per-turn, per-session, per-Repository, and per-user AI Cost figures are all
    sums of these rows, grouped by their attribution columns. ``cost`` is derived
    (never provider-reported) and is ``null`` when the served model is missing
    from the local price table. The turn anchors ``session_history_id`` and
    ``coding_run_id`` are mutually exclusive — a Repository question stamps the
    first, a Code Generation Task the second — and both may be null transiently
    before the turn is stamped.
    """

    __tablename__ = "usage_record"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # The model id and provider that actually served the call (the response's model, not the configured primary).
    model: str = Field(max_length=255)
    provider: str = Field(max_length=255)
    # The originating graph node, retained for later per-node breakdowns.
    node_name: str = Field(max_length=255)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    # Derived cost = input_tokens x input_rate + output_tokens x output_rate; null for an unpriced model.
    cost: float | None = Field(default=None)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True, ondelete="CASCADE")
    repository_id: uuid.UUID = Field(foreign_key="repository.id", nullable=False, index=True, ondelete="CASCADE")
    repository_session_id: uuid.UUID = Field(foreign_key="repository_session.id", nullable=False, index=True, ondelete="CASCADE")
    session_history_id: uuid.UUID | None = Field(default=None, foreign_key="session_history.id", index=True, ondelete="CASCADE")
    coding_run_id: uuid.UUID | None = Field(default=None, foreign_key="coding_run.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore
