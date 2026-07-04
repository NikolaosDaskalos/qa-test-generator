"""The PostgreSQL store for Usage Records, the durable ledger behind AI Cost."""

import uuid

from sqlmodel import Session, col, select

from app.db.models import UsageRecord


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
