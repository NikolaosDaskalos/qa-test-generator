"""Unit tests for the Repository Session execution-context assembly.

The context is exercised on plain inputs only — no graph is compiled or run.
"""

import uuid

from langchain_core.messages import AIMessage, HumanMessage

from app.enums import SessionMessageRole
from app.models import Repository, RepositorySession, SessionHistory
from app.services import RepositorySessionExecution


def _repository(**overrides) -> Repository:
    fields = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "name": "r",
        "repository_url": "https://github.com/o/r.git",
        "owner": "o",
        "local_path": "/checkout",
        "indexed_commit_sha": "a" * 40,
    }
    fields.update(overrides)
    return Repository(**fields)


def _session(repository: Repository) -> RepositorySession:
    return RepositorySession(id=uuid.uuid4(), owner_id=repository.user_id, repository_id=repository.id)


def test_graph_input_carries_session_ids_and_resolved_checkout_fields():
    repository = _repository()
    session = _session(repository)
    context = RepositorySessionExecution.assemble(repository_session=session, repository=repository, history=[])

    graph_input = context.graph_input("how do I run the tests?")

    assert graph_input["question"] == "how do I run the tests?"
    assert graph_input["repository_id"] == session.repository_id
    assert graph_input["repository_session_id"] == session.id
    assert graph_input["checkout_root"] == "/checkout"
    assert graph_input["indexed_commit_sha"] == "a" * 40


def test_missing_repository_resolves_checkout_fields_to_none():
    repository = _repository()
    session = _session(repository)
    context = RepositorySessionExecution.assemble(repository_session=session, repository=None, history=[])

    graph_input = context.graph_input("q")

    assert graph_input["checkout_root"] is None
    assert graph_input["indexed_commit_sha"] is None
    # The session identity is still carried even without a bound checkout.
    assert graph_input["repository_session_id"] == session.id


def _history_row(session, role, content, position):
    return SessionHistory(id=uuid.uuid4(), session_id=session.id, role=role, content=content, position=position)


def test_history_window_projects_roles_in_order_then_appends_the_question():
    repository = _repository()
    session = _session(repository)
    history = [_history_row(session, SessionMessageRole.user, "first question", 1), _history_row(session, SessionMessageRole.assistant, "first answer", 2)]
    context = RepositorySessionExecution.assemble(repository_session=session, repository=repository, history=history)

    messages = context.graph_input("next question")["messages"]

    assert [(type(m), m.content) for m in messages] == [(HumanMessage, "first question"), (AIMessage, "first answer"), (HumanMessage, "next question")]
