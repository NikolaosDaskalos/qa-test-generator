"""The PostgreSQL store for Repository Sessions and their ordered message history."""

import re
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, col, func, select

from app.core import settings
from app.db.models import LEGACY_NEW_SESSION_TITLE, MAX_DERIVED_SESSION_TITLE_LENGTH, NEW_SESSION_TITLE, CitationData, RepositorySession, SessionHistory
from app.enums import SessionMessageRole

_WHITESPACE_RE = re.compile(r"\s+")
_PLACEHOLDER_TITLES = {NEW_SESSION_TITLE, LEGACY_NEW_SESSION_TITLE}


class RepositorySessionStore:
    """Persist Repository Sessions through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, repository_session: RepositorySession) -> RepositorySession:
        """Persist a session and return the refreshed row."""
        self.session.add(repository_session)
        self.session.commit()
        self.session.refresh(repository_session)
        return repository_session

    def get_by_id(self, repository_session_id: uuid.UUID) -> RepositorySession | None:
        """Load a session by id, or ``None`` if absent."""
        return self.session.get(RepositorySession, repository_session_id)

    def get_page(self, *, skip: int, limit: int, user_id: uuid.UUID | None = None, repository_id: uuid.UUID | None = None) -> list[RepositorySession]:
        """Return a page of sessions, most-recently-active first, optionally scoped by owner/repository."""
        statement = self._scoped(select(RepositorySession), user_id=user_id, repository_id=repository_id)
        statement = statement.order_by(col(RepositorySession.updated_at).desc(), col(RepositorySession.id)).offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def append_exchange(
        self, repository_session_id: uuid.UUID, *, user_message: str, assistant_message: str, assistant_citations: list[CitationData] | None = None
    ) -> tuple[SessionHistory, SessionHistory]:
        """Append a user/assistant message pair at the next positions under a row lock.

        Locks the session row to serialize position assignment, touches its activity
        timestamp, and derives a title from the first real user message.
        """
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
        """Touch session activity and derive a title from ``user_message`` without storing it."""
        lock_statement = select(RepositorySession).where(RepositorySession.id == repository_session_id).with_for_update()
        repository_session = self.session.exec(lock_statement).one()
        _touch_session_activity(repository_session, user_message=user_message)
        self.session.add(repository_session)
        self.session.commit()

    def record_activity(self, repository_session_id: uuid.UUID) -> None:
        """Bump a session's activity timestamp without changing its title."""
        lock_statement = select(RepositorySession).where(RepositorySession.id == repository_session_id).with_for_update()
        repository_session = self.session.exec(lock_statement).one()
        _touch_session_activity(repository_session)
        self.session.add(repository_session)
        self.session.commit()

    def count(self, *, user_id: uuid.UUID | None = None, repository_id: uuid.UUID | None = None) -> int:
        """Count sessions, optionally scoped by owner and/or repository."""
        statement = self._scoped(select(func.count()).select_from(RepositorySession), user_id=user_id, repository_id=repository_id)
        return self.session.exec(statement).one()

    @staticmethod
    def _scoped(statement, *, user_id: uuid.UUID | None, repository_id: uuid.UUID | None):
        """Apply optional owner/repository filters to a session query."""
        if user_id is not None:
            statement = statement.where(RepositorySession.user_id == user_id)
        if repository_id is not None:
            statement = statement.where(RepositorySession.repository_id == repository_id)
        return statement

    def get_recent_history(self, repository_session_id: uuid.UUID) -> list[SessionHistory]:
        """Return the last ``SESSION_HISTORY_LIMIT`` messages in chronological order."""
        statement = (
            select(SessionHistory)
            .where(SessionHistory.session_id == repository_session_id)
            .order_by(col(SessionHistory.position).desc())
            .limit(settings.SESSION_HISTORY_LIMIT)
        )
        return list(reversed(self.session.exec(statement).all()))


def _derive_session_title(user_message: str) -> str:
    """Build a session title from a user message, trimmed at a word boundary to the max length."""
    normalized = _WHITESPACE_RE.sub(" ", user_message).strip()
    if len(normalized) <= MAX_DERIVED_SESSION_TITLE_LENGTH:
        return normalized
    truncated = normalized[:MAX_DERIVED_SESSION_TITLE_LENGTH].rstrip()
    word_boundary = truncated.rfind(" ")
    if word_boundary <= 0:
        return truncated
    return truncated[:word_boundary]


def _touch_session_activity(repository_session: RepositorySession, *, user_message: str | None = None) -> None:
    """Bump ``updated_at``, and replace a placeholder title with one derived from ``user_message``."""
    repository_session.updated_at = datetime.now(UTC)
    if user_message is None:
        return
    derived_title = _derive_session_title(user_message)
    if repository_session.title in _PLACEHOLDER_TITLES and derived_title:
        repository_session.title = derived_title
