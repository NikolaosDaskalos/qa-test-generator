"""The PostgreSQL store for Usage Records, the durable ledger behind AI Cost."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.db.models import UsageRecord


@dataclass(frozen=True)
class CostTotals:
    """The summed AI Cost and token totals of a set of Usage Records.

    Records with a ``null`` cost (an unpriced model) contribute their tokens but
    nothing to ``cost`` — SQL ``SUM`` skips the nulls — so an all-unpriced set
    reads back a well-defined ``cost`` of zero, never null.
    """

    cost: float
    input_tokens: int
    output_tokens: int
    total_tokens: int


class UsageRecordStore:
    """Persist and read back Usage Records through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id: uuid.UUID,
        repository_id: uuid.UUID,
        repository_session_id: uuid.UUID,
        model: str,
        provider: str,
        node_name: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cost: float | None,
        session_history_id: uuid.UUID | None = None,
        coding_run_id: uuid.UUID | None = None,
    ) -> UsageRecord:
        """Insert one metered LLM call with its attribution and return the refreshed row."""
        record = UsageRecord(
            user_id=user_id,
            repository_id=repository_id,
            repository_session_id=repository_session_id,
            model=model,
            provider=provider,
            node_name=node_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            session_history_id=session_history_id,
            coding_run_id=coding_run_id,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list(
        self,
        *,
        user_id: uuid.UUID | None = None,
        repository_id: uuid.UUID | None = None,
        repository_session_id: uuid.UUID | None = None,
        session_history_id: uuid.UUID | None = None,
        coding_run_id: uuid.UUID | None = None,
    ) -> list[UsageRecord]:
        """Return the records matching every supplied attribution filter, oldest first."""
        statement = select(UsageRecord)
        if user_id is not None:
            statement = statement.where(UsageRecord.user_id == user_id)
        if repository_id is not None:
            statement = statement.where(UsageRecord.repository_id == repository_id)
        if repository_session_id is not None:
            statement = statement.where(UsageRecord.repository_session_id == repository_session_id)
        if session_history_id is not None:
            statement = statement.where(UsageRecord.session_history_id == session_history_id)
        if coding_run_id is not None:
            statement = statement.where(UsageRecord.coding_run_id == coding_run_id)
        statement = statement.order_by(col(UsageRecord.created_at), col(UsageRecord.id))
        return list(self.session.exec(statement).all())

    def totals(
        self,
        *,
        user_id: uuid.UUID | None = None,
        repository_id: uuid.UUID | None = None,
        repository_session_id: uuid.UUID | None = None,
    ) -> CostTotals:
        """Sum the AI Cost and token totals of the records matching every supplied filter.

        With no filter it rolls up every record (the superuser-only all-users total). An
        unpriced record's ``null`` cost is skipped by ``SUM`` while its tokens still count,
        and an empty set coalesces to a zeroed total rather than nulls.
        """
        statement = select(
            func.coalesce(func.sum(UsageRecord.cost), 0.0),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        )
        if user_id is not None:
            statement = statement.where(UsageRecord.user_id == user_id)
        if repository_id is not None:
            statement = statement.where(UsageRecord.repository_id == repository_id)
        if repository_session_id is not None:
            statement = statement.where(UsageRecord.repository_session_id == repository_session_id)
        cost, input_tokens, output_tokens, total_tokens = self.session.exec(statement).one()
        return CostTotals(cost=float(cost), input_tokens=int(input_tokens), output_tokens=int(output_tokens), total_tokens=int(total_tokens))
