import uuid

from sqlmodel import Session, col, func, select

from app.enums.session import SessionMessageRole
from app.models.session import RepositorySession, SessionHistory


class RepositorySessionStore:
    """Persist Repository Sessions through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, repository_session: RepositorySession) -> RepositorySession:
        self.session.add(repository_session)
        self.session.commit()
        self.session.refresh(repository_session)
        return repository_session

    def get_by_id(self, repository_session_id: uuid.UUID) -> RepositorySession | None:
        return self.session.get(RepositorySession, repository_session_id)

    def append_exchange(self, repository_session_id: uuid.UUID, *, user_message: str, assistant_message: str) -> tuple[SessionHistory, SessionHistory]:
        lock_statement = select(RepositorySession.id).where(RepositorySession.id == repository_session_id).with_for_update()
        self.session.exec(lock_statement).one()
        position_statement = select(func.max(SessionHistory.position)).where(SessionHistory.session_id == repository_session_id)
        next_position = (self.session.exec(position_statement).one() or 0) + 1
        user_history = SessionHistory(session_id=repository_session_id, role=SessionMessageRole.user, content=user_message, position=next_position)
        assistant_history = SessionHistory(
            session_id=repository_session_id, role=SessionMessageRole.assistant, content=assistant_message, position=next_position + 1
        )
        self.session.add(user_history)
        self.session.add(assistant_history)
        self.session.commit()
        self.session.refresh(user_history)
        self.session.refresh(assistant_history)
        return user_history, assistant_history

    def get_recent_history(self, repository_session_id: uuid.UUID) -> list[SessionHistory]:
        statement = select(SessionHistory).where(SessionHistory.session_id == repository_session_id).order_by(col(SessionHistory.position).desc()).limit(6)
        return list(reversed(self.session.exec(statement).all()))
