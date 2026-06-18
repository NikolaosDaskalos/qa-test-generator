import re
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.enums.session import SessionMessageRole
from app.models.session import (
    LEGACY_NEW_SESSION_TITLE,
    MAX_DERIVED_SESSION_TITLE_LENGTH,
    NEW_SESSION_TITLE,
    CitationData,
    RepositorySession,
    SessionHistory,
)


_WHITESPACE_RE = re.compile(r"\s+")
_PLACEHOLDER_TITLES = {NEW_SESSION_TITLE, LEGACY_NEW_SESSION_TITLE}


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

    def get_page(
        self, *, skip: int, limit: int, owner_id: uuid.UUID | None = None, repository_id: uuid.UUID | None = None
    ) -> list[RepositorySession]:
        statement = self._scoped(select(RepositorySession), owner_id=owner_id, repository_id=repository_id)
        statement = statement.order_by(col(RepositorySession.updated_at).desc(), col(RepositorySession.id)).offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def append_exchange(
            self, repository_session_id: uuid.UUID, *, user_message: str, assistant_message: str, assistant_citations: list[CitationData] | None = None
    ) -> tuple[SessionHistory, SessionHistory]:
        lock_statement = select(RepositorySession).where(RepositorySession.id == repository_session_id).with_for_update()
        repository_session = self.session.exec(lock_statement).one()
        position_statement = select(func.max(SessionHistory.position)).where(SessionHistory.session_id == repository_session_id)
        next_position = (self.session.exec(position_statement).one() or 0) + 1
        user_history = SessionHistory(session_id=repository_session_id, role=SessionMessageRole.user, content=user_message, position=next_position)
        assistant_history = SessionHistory(
            session_id=repository_session_id,
            role=SessionMessageRole.assistant,
            content=assistant_message,
            citations=assistant_citations or [],
            position=next_position + 1,
        )
        if isinstance(repository_session, RepositorySession):
            _touch_session_activity(repository_session, user_message=user_message)
            self.session.add(repository_session)
        self.session.add(user_history)
        self.session.add(assistant_history)
        self.session.commit()
        self.session.refresh(user_history)
        self.session.refresh(assistant_history)
        return user_history, assistant_history

    def record_user_activity(self, repository_session_id: uuid.UUID, *, user_message: str) -> None:
        lock_statement = select(RepositorySession).where(RepositorySession.id == repository_session_id).with_for_update()
        repository_session = self.session.exec(lock_statement).one()
        _touch_session_activity(repository_session, user_message=user_message)
        self.session.add(repository_session)
        self.session.commit()

    def record_activity(self, repository_session_id: uuid.UUID) -> None:
        lock_statement = select(RepositorySession).where(RepositorySession.id == repository_session_id).with_for_update()
        repository_session = self.session.exec(lock_statement).one()
        _touch_session_activity(repository_session)
        self.session.add(repository_session)
        self.session.commit()

    def count(self, *, owner_id: uuid.UUID | None = None, repository_id: uuid.UUID | None = None) -> int:
        statement = self._scoped(select(func.count()).select_from(RepositorySession), owner_id=owner_id, repository_id=repository_id)
        return self.session.exec(statement).one()

    @staticmethod
    def _scoped(statement, *, owner_id: uuid.UUID | None, repository_id: uuid.UUID | None):
        if owner_id is not None:
            statement = statement.where(RepositorySession.owner_id == owner_id)
        if repository_id is not None:
            statement = statement.where(RepositorySession.repository_id == repository_id)
        return statement

    def get_recent_history(self, repository_session_id: uuid.UUID) -> list[SessionHistory]:
        statement = (select(SessionHistory)
                     .where(SessionHistory.session_id == repository_session_id)
                     .order_by(col(SessionHistory.position).desc())
                     .limit(settings.SESSION_HISTORY_LIMIT))
        return list(reversed(self.session.exec(statement).all()))


def _derive_session_title(user_message: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", user_message).strip()
    if len(normalized) <= MAX_DERIVED_SESSION_TITLE_LENGTH:
        return normalized
    truncated = normalized[:MAX_DERIVED_SESSION_TITLE_LENGTH].rstrip()
    word_boundary = truncated.rfind(" ")
    if word_boundary <= 0:
        return truncated
    return truncated[:word_boundary]


def _touch_session_activity(repository_session: RepositorySession, *, user_message: str | None = None) -> None:
    repository_session.updated_at = datetime.now(UTC)
    if user_message is None:
        return
    derived_title = _derive_session_title(user_message)
    if repository_session.title in _PLACEHOLDER_TITLES and derived_title:
        repository_session.title = derived_title
