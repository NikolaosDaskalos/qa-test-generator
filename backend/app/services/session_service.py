import uuid
from collections.abc import Generator
from typing import Any, Protocol

from fastapi import HTTPException, status

from app.enums.repository import RepositoryStatus
from app.models.session import RepositorySession, SessionHistory
from app.models.user import User
from app.persistence.repository_store import RepositoryStore
from app.persistence.session_store import RepositorySessionStore
from app.schemas.agent_stream import AgentStreamEvent, Citation, Citations, Result, Sources, Stage, Token
from app.schemas.session import RepositorySessionCreate


class AnswerPipeline(Protocol):
    """The repository-scoped answer source consumed when answering a question."""

    def answer_stream(self, question: str, *, repository_id: uuid.UUID, history: list[dict[str, Any]]) -> Generator[AgentStreamEvent, None, None]: ...


class RepositorySessionService:
    """Own Repository Session authorization and lifecycle rules."""

    def __init__(self, session_store: RepositorySessionStore, repository_store: RepositoryStore) -> None:
        self.session_store = session_store
        self.repository_store = repository_store

    def create_session(self, *, session_in: RepositorySessionCreate, user: User) -> RepositorySession:
        repository = self.repository_store.get_by_id(session_in.repository_id)
        if not repository:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if repository.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        if repository.status != RepositoryStatus.ready:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is not ready")

        return self.session_store.save(RepositorySession(owner_id=user.id, repository_id=repository.id, title=session_in.title))

    def get_recent_history(self, *, repository_session_id: uuid.UUID, user: User) -> list[SessionHistory]:
        repository_session = self._get_accessible(repository_session_id, user)
        return self.session_store.get_recent_history(repository_session.id)

    def record_exchange(
        self, *, repository_session_id: uuid.UUID, user: User, user_message: str, assistant_message: str
    ) -> tuple[SessionHistory, SessionHistory]:
        repository_session = self._get_accessible(repository_session_id, user)
        return self.session_store.append_exchange(repository_session.id, user_message=user_message, assistant_message=assistant_message)

    def answer_question(
        self, *, repository_session_id: uuid.UUID, user: User, question: str, pipeline: AnswerPipeline
    ) -> Generator[AgentStreamEvent, None, None]:
        """Stream a repository-grounded answer and persist the completed exchange.

        Ownership is enforced before any streaming begins. The returned generator
        emits ordered stage progress, answer tokens, file citations, and one
        terminal result that reflects the persisted Session History.
        """
        repository_session = self._get_accessible(repository_session_id, user)
        history = [{"role": message.role.value, "content": message.content} for message in self.session_store.get_recent_history(repository_session.id)]
        return self._stream_answer(repository_session, question, history, pipeline)

    def _stream_answer(
        self, repository_session: RepositorySession, question: str, history: list[dict[str, Any]], pipeline: AnswerPipeline
    ) -> Generator[AgentStreamEvent, None, None]:
        yield Stage(stage="retrieving")
        answer = ""
        sources: list[str] = []
        generating = False
        for event in pipeline.answer_stream(question, repository_id=repository_session.repository_id, history=history):
            if isinstance(event, Token):
                if not event.content:
                    continue
                if not generating:
                    generating = True
                    yield Stage(stage="generating")
                answer += event.content
                yield event
            elif isinstance(event, Sources):
                # Internal hop: collected to build citations, never forwarded to the wire.
                sources = event.sources
            else:
                yield event

        citations = self._to_citations(sources)
        _user_message, assistant_message = self.session_store.append_exchange(
            repository_session.id, user_message=question, assistant_message=self._with_citation_footer(answer, citations)
        )
        yield Citations(citations=citations)
        yield Result(
            repository_session_id=repository_session.id,
            assistant_message_id=assistant_message.id,
            answer=answer,
            citations=citations,
        )

    @staticmethod
    def _to_citations(sources: list[str]) -> list[Citation]:
        """Project retrieved source paths into file citations, de-duplicated in order."""
        citations: list[Citation] = []
        seen: set[str] = set()
        for path in sources:
            if path and path not in seen:
                seen.add(path)
                citations.append(Citation(source=path))
        return citations

    @staticmethod
    def _with_citation_footer(answer: str, citations: list[Citation]) -> str:
        """Append a traceable source footer that history reformulation later strips."""
        if not citations:
            return answer
        paths = ", ".join(citation.source for citation in citations)
        return f"{answer}\n\n---\n📚 Sources: {paths}"

    def _get_accessible(self, repository_session_id: uuid.UUID, user: User) -> RepositorySession:
        repository_session = self.session_store.get_by_id(repository_session_id)
        if not repository_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository Session not found")
        if repository_session.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return repository_session
