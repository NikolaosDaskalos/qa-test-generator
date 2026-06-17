"""Assemble what the unified graph needs to run for one Repository Session."""

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.enums.session import SessionMessageRole
from app.models.repository import Repository
from app.models.session import RepositorySession, SessionHistory


@dataclass(frozen=True)
class RepositorySessionExecution:
    """The graph's per-session execution context, built from plain inputs."""

    repository_session: RepositorySession
    history: list[SessionHistory]
    checkout_root: str | None
    indexed_commit_sha: str | None

    @classmethod
    def assemble(
        cls, *, repository_session: RepositorySession, repository: Repository | None, history: list[SessionHistory]
    ) -> "RepositorySessionExecution":
        """Resolve the bound Repository's checkout fields, falling back to ``None`` when it is missing."""
        return cls(
            repository_session=repository_session,
            history=history,
            checkout_root=repository.local_path if repository else None,
            indexed_commit_sha=repository.indexed_commit_sha if repository else None,
        )

    def graph_input(self, question: str) -> dict[str, Any]:
        """Build the graph input dict for one answering/test-generation turn."""
        return {
            "messages": [*self._to_messages(), HumanMessage(content=question)],
            "question": question,
            "repository_id": self.repository_session.repository_id,
            "repository_session_id": self.repository_session.id,
            "checkout_root": self.checkout_root,
            "indexed_commit_sha": self.indexed_commit_sha,
        }

    def _to_messages(self) -> list[BaseMessage]:
        """Project the recent Session History window into LangChain messages for the graph spine."""
        return [
            AIMessage(content=row.content) if row.role == SessionMessageRole.assistant else HumanMessage(content=row.content)
            for row in self.history
        ]
