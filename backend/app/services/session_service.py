import uuid
from collections.abc import Generator
from typing import Any

from fastapi import HTTPException, status
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.stream import map_graph_stream
from app.enums.repository import RepositoryStatus
from app.enums.session import SessionMessageRole
from app.models.session import RepositorySession, SessionHistory
from app.models.user import User
from app.persistence.repository_store import RepositoryStore
from app.persistence.session_store import RepositorySessionStore
from app.schemas.agent_stream import AgentStreamEvent, Result
from app.schemas.session import RepositorySessionCreate


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

    def stream_session(
        self, *, repository_session_id: uuid.UUID, user: User, question: str, graph: Any, thread_id: str
    ) -> Generator[AgentStreamEvent, None, None]:
        """Drive the unified intent-routed graph for one owned session.

        Ownership is enforced before streaming. In-flight stage/token/run markers
        pass straight through; the terminal event is decided from the graph's
        final state — a repository answer is persisted and reported as ``Result``,
        while a rejected Test-Generation Task surfaces its ``RunFailure``.
        """
        repository_session = self._get_accessible(repository_session_id, user)
        history = [{"role": message.role.value, "content": message.content} for message in self.session_store.get_recent_history(repository_session.id)]
        repository = self.repository_store.get_by_id(repository_session.repository_id)
        checkout_root = repository.local_path if repository else None
        indexed_commit_sha = repository.indexed_commit_sha if repository else None
        return self._stream_session(repository_session, question, history, checkout_root, indexed_commit_sha, graph, thread_id)

    def _stream_session(
        self,
        repository_session: RepositorySession,
        question: str,
        history: list[dict[str, Any]],
        checkout_root: str | None,
        indexed_commit_sha: str | None,
        graph: Any,
        thread_id: str,
    ) -> Generator[AgentStreamEvent, None, None]:
        config = {"configurable": {"thread_id": thread_id}}
        graph_input = {
            "messages": [*self._to_messages(history), HumanMessage(content=question)],
            "question": question,
            "repository_id": repository_session.repository_id,
            "repository_session_id": repository_session.id,
            "checkout_root": checkout_root,
            "indexed_commit_sha": indexed_commit_sha,
        }
        yield from map_graph_stream(graph.stream(graph_input, config=config, stream_mode=["custom", "messages"]))

        final = graph.get_state(config).values
        failure = final.get("failure")
        if failure is not None:
            yield failure
            return
        patch_result = final.get("patch_result")
        if patch_result is not None:
            yield patch_result
            return
        if final.get("intent") == "repository_question":
            answer = final.get("answer", "")
            citations = final.get("citations", [])
            _user_message, assistant_message = self.session_store.append_exchange(
                repository_session.id,
                user_message=question,
                assistant_message=answer,
                assistant_citations=[citation.model_dump() for citation in citations],
            )
            yield Result(
                repository_session_id=repository_session.id,
                assistant_message_id=assistant_message.id,
                answer=answer,
                citations=citations,
            )

    @staticmethod
    def _to_messages(history: list[dict[str, Any]]) -> list[BaseMessage]:
        """Project recent Session History rows into LangChain messages for the graph spine."""
        return [
            AIMessage(content=entry["content"]) if entry["role"] == SessionMessageRole.assistant.value else HumanMessage(content=entry["content"])
            for entry in history
        ]

    def _get_accessible(self, repository_session_id: uuid.UUID, user: User) -> RepositorySession:
        repository_session = self.session_store.get_by_id(repository_session_id)
        if not repository_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository Session not found")
        if repository_session.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return repository_session
