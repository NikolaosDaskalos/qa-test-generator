"""The Repository Session application service: ownership rules, history, and graph streaming."""

import uuid
from collections.abc import Generator
from typing import Any

from fastapi import HTTPException, status
from langgraph.types import Command

from app.enums import RepositoryStatus
from app.models import CodingRun, RepositorySession, SessionHistory, User
from app.persistence import CodingRunStore, RepositorySessionStore, RepositoryStore
from app.schemas import AgentStreamEvent, HumanDecisionRequest, RepositorySessionCreate, RepositorySessionsPublic, Result, RunApproved, RunRejected
from app.services.repository_session_execution import RepositorySessionExecution
from app.streaming import map_graph_stream


class RepositorySessionService:
    """Own Repository Session authorization and lifecycle rules."""

    def __init__(self, session_store: RepositorySessionStore, repository_store: RepositoryStore, coding_run_store: CodingRunStore | None = None) -> None:
        self.session_store = session_store
        self.repository_store = repository_store
        self.coding_run_store = coding_run_store

    def create_session(self, *, session_in: RepositorySessionCreate, user: User) -> RepositorySession:
        """Open a session, requiring the caller to own a ready repository (404/403/409 otherwise)."""
        repository = self.repository_store.get_by_id(session_in.repository_id)
        if not repository:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if repository.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        if repository.status != RepositoryStatus.ready:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository is not ready")

        return self.session_store.save(RepositorySession(owner_id=user.id, repository_id=repository.id))

    def list_sessions(self, *, user: User, repository_id: uuid.UUID | None, skip: int, limit: int) -> RepositorySessionsPublic:
        """List the caller's Repository Sessions, optionally filtered to one Repository.

        Sessions are scoped by ownership with a superuser bypass. A supplied
        ``repository_id`` is validated like a read — a missing Repository is a 404
        and one the caller does not own is a 403 (superuser bypassed) — but the
        readiness gate that guards session creation is deliberately not applied, so
        a still-indexing or failed Repository's sessions remain listable.
        """
        if repository_id is not None:
            self._assert_repository_readable(repository_id, user)
        owner_id = None if user.is_superuser else user.id
        sessions = self.session_store.get_page(skip=skip, limit=limit, owner_id=owner_id, repository_id=repository_id)
        count = self.session_store.count(owner_id=owner_id, repository_id=repository_id)
        return RepositorySessionsPublic(data=sessions, count=count)  # type: ignore[arg-type]

    def _assert_repository_readable(self, repository_id: uuid.UUID, user: User) -> None:
        """Raise 404/403 unless the caller can read the repository (superuser bypass)."""
        repository = self.repository_store.get_by_id(repository_id)
        if not repository:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
        if not user.is_superuser and repository.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    def get_recent_history(self, *, repository_session_id: uuid.UUID, user: User) -> list[SessionHistory]:
        """Return an owned session's recent message history."""
        repository_session = self._get_accessible(repository_session_id, user)
        return self.session_store.get_recent_history(repository_session.id)

    def get_owned_run(self, *, repository_session_id: uuid.UUID, coding_run_id: uuid.UUID, user: User) -> CodingRun:
        """Return a Coding Run the user owns through the named session, else 404.

        Ownership flows through the session: the session must be accessible to the
        user and the run must belong to that session, so a run cannot be read via a
        session the caller does not own.
        """
        repository_session = self._get_accessible(repository_session_id, user)
        run = self.coding_run_store.get_by_id(coding_run_id) if self.coding_run_store else None
        if run is None or run.repository_session_id != repository_session.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding Run not found")
        return run

    def record_exchange(
        self, *, repository_session_id: uuid.UUID, user: User, user_message: str, assistant_message: str
    ) -> tuple[SessionHistory, SessionHistory]:
        """Append a user/assistant message pair to an owned session."""
        repository_session = self._get_accessible(repository_session_id, user)
        return self.session_store.append_exchange(repository_session.id, user_message=user_message, assistant_message=assistant_message)

    def stream_session(
        self, *, repository_session_id: uuid.UUID, user: User, question: str | None, graph: Any, thread_id: str, decision: HumanDecisionRequest | None = None
    ) -> Generator[AgentStreamEvent, None, None]:
        """Drive the unified intent-routed graph for one owned session.

        Ownership is enforced before streaming. In-flight stage/token/run markers
        pass straight through. Code-generation terminal events are emitted by
        their producing graph node and relayed from the stream, superseding the
        older "caller decides from final state" contract. Repository answers
        still use final state so the exchange can be persisted before reporting
        the terminal ``Result`` with its stored assistant message id.

        When a human-in-the-loop ``decision`` is supplied the same entry point
        resumes the suspended Coding Run that produced the patch instead of
        starting a new run, so the owner's approve/reject decision flows back into
        the paused graph rather than through a separate endpoint.
        """
        if decision is not None:
            return self._resume_decision(repository_session_id=repository_session_id, user=user, decision=decision, graph=graph)

        repository_session = self._get_accessible(repository_session_id, user)
        self.session_store.record_user_activity(repository_session.id, user_message=question)
        repository = self.repository_store.get_by_id(repository_session.repository_id)
        context = RepositorySessionExecution.assemble(
            repository_session=repository_session, repository=repository, history=self.session_store.get_recent_history(repository_session.id)
        )
        return self._stream_session(context, question, graph, thread_id)

    def _stream_session(self, context: RepositorySessionExecution, question: str, graph: Any, thread_id: str) -> Generator[AgentStreamEvent, None, None]:
        """Stream a fresh turn, persisting the exchange and emitting the terminal ``Result`` for answers."""
        repository_session = context.repository_session
        config = {"configurable": {"thread_id": thread_id}}
        yield from map_graph_stream(graph.stream(context.graph_input(question), config=config, stream_mode=["custom", "messages"]))

        final = graph.get_state(config).values
        if final.get("intent") == "repository_question":
            answer = final.get("answer", "")
            citations = final.get("citations", [])
            _user_message, assistant_message = self.session_store.append_exchange(
                repository_session.id, user_message=question, assistant_message=answer, assistant_citations=[citation.model_dump() for citation in citations]
            )
            yield Result(repository_session_id=repository_session.id, assistant_message_id=assistant_message.id, answer=answer, citations=citations)

    def _resume_decision(
        self, *, repository_session_id: uuid.UUID, user: User, decision: HumanDecisionRequest, graph: Any
    ) -> Generator[AgentStreamEvent, None, None]:
        """Validate ownership and state, then resume the suspended run with the decision.

        Ownership flows through the session and the run; only a run actually paused
        for a decision (``awaiting_approval``) is resumable, so a repeated decision
        or one for any other state is rejected before the graph — and the shared
        checkout — is ever touched.
        """
        run = self.get_owned_run(repository_session_id=repository_session_id, coding_run_id=decision.coding_run_id, user=user)
        if not run.awaiting_decision:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Coding Run is not awaiting a decision")
        self._assert_checkpoint_awaits_decision(run, graph)
        return self._resume_stream(run, decision, graph)

    def _resume_stream(self, run: CodingRun, decision: HumanDecisionRequest, graph: Any) -> Generator[AgentStreamEvent, None, None]:
        """Resume a paused Coding Run and relay node-emitted terminal events."""
        config = {"configurable": {"thread_id": run.thread_id}}
        command = Command(resume={"approved": decision.approved, "feedback": decision.feedback})
        for event in map_graph_stream(graph.stream(command, config=config, stream_mode=["custom", "messages"])):
            if isinstance(event, RunApproved | RunRejected):
                self.session_store.record_activity(run.repository_session_id)
            yield event

    @staticmethod
    def _assert_checkpoint_awaits_decision(run: CodingRun, graph: Any) -> None:
        """Reject stale awaiting-approval runs whose LangGraph thread is not paused."""
        config = {"configurable": {"thread_id": run.thread_id}}
        state = graph.get_state(config)
        pending_nodes = tuple(getattr(state, "next", ()) or ())
        if "await_decision" not in pending_nodes:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Coding Run is not awaiting a decision")

    def _get_accessible(self, repository_session_id: uuid.UUID, user: User) -> RepositorySession:
        """Return a session the user owns, raising 404 if missing or 403 if not theirs."""
        repository_session = self.session_store.get_by_id(repository_session_id)
        if not repository_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository Session not found")
        if repository_session.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return repository_session
