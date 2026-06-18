"""The unified intent-routed LangGraph for repository sessions.

A single ``StateGraph`` over one shared state object infers the Request Intent in
a ``classify`` node and routes to one of two branches: ``repository_question``
(retrieval-grounded answer) or ``test_generation`` (a bounded plan/retrieve run).
The graph is compiled with a checkpointer (the durable ``PostgresSaver`` in
production, an ephemeral ``MemorySaver`` in tests) so a per-run ``thread_id``
carries in-flight state, leaving room for later human-in-the-loop interrupts
without re-architecting.
"""

import operator
import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.services.coding_runs.patch_publisher import NullPatchPublisher
from app.agent.nodes.planner import build_plan_node
from app.agent.nodes.repository_question import build_generate_node, build_retrieve_node
from app.services.coding_runs.recorder import NullRunRecorder
from app.streaming.agent_stream import emit
from app.agent.nodes.test_generation import (
    build_approve_patch_node,
    build_await_decision_node,
    build_build_patch_node,
    build_discard_patch_node,
    build_gather_evidence_node,
    build_generate_tests_node,
    build_prepare_branch_node,
    build_review_gate_node,
    build_review_patch_node,
    build_revise_tests_node,
)
from app.services.coding_runs.workspace import LocalGitWorkspace
from app.schemas.agent_stream import Citation, PatchResult, ReviewResult, RunApproved, RunFailure, RunRejected, Stage
from app.schemas.research_intent import ResearchIntent

Intent = Literal["repository_question", "test_generation"]


class Classification(BaseModel):
    """Structured output of the ``classify`` node."""

    intent: Intent = Field(description="Route the user's request to either a read-only repository question or a test-generation coding run.")


class GraphState(TypedDict, total=False):
    """The single shared state threaded through every node."""

    # The LangChain-native message spine: recent Session History plus the current
    # turn, reduced with ``add_messages``. ``classify`` reads it so follow-ups
    # ("now write tests for that") route on conversational context, not the bare
    # question. ``question`` stays as the plain retrieval/planning query string.
    messages: Annotated[list, add_messages]
    question: str
    repository_id: uuid.UUID
    repository_session_id: uuid.UUID
    coding_run_id: uuid.UUID
    intent: Intent
    checkout_root: str
    indexed_commit_sha: str
    evidence: list
    answer: str
    citations: list[Citation]
    research_intents: list[ResearchIntent]
    source_evidence: list
    test_evidence: list
    candidate_hints: list[str]
    generation_branch: str
    generated_files: list
    external_references: list
    diff: str
    patch_result: PatchResult
    review_result: ReviewResult
    # Serialized count of spent Revision Attempts. Its semantics live in
    # ``RevisionBudget``.
    revision_attempts: int
    # The owner's human-in-the-loop decision on an accepted patch, supplied by resuming
    # the suspended graph, and the terminal outcome when that decision is a rejection.
    approved: bool
    human_feedback: str
    rejection_result: RunRejected
    approval_result: RunApproved
    failure: RunFailure
    trace: Annotated[list[str], operator.add]


def _classify_node(classifier_llm):
    """Build the classify node; uncertain classification falls back to read-only."""
    structured = classifier_llm.with_structured_output(Classification)

    def classify(state: GraphState) -> dict:
        emit(Stage(stage="classifying"))
        # Read recent Session History when present; fall back to the bare question.
        messages = state.get("messages") or [HumanMessage(content=state["question"])]
        result = structured.invoke(messages)
        intent: Intent = result.intent if result else "repository_question"
        return {"intent": intent, "trace": ["classify"]}

    return classify


def _route_intent(state: GraphState) -> Intent:
    return state.get("intent", "repository_question")


def _route_after_plan(state: GraphState) -> Literal["failed", "planned"]:
    return "failed" if state.get("failure") else "planned"


def _route_after_decision(state: GraphState) -> Literal["approve", "reject"]:
    """Route the owner's human-in-the-loop decision on an accepted Test Patch.

    Resuming the suspended graph supplies the decision; a rejection discards the patch
    while an approval commits and pushes its branch. The decision defaults closed to
    neither acting nor discarding silently: only an explicit ``approved`` truthy value
    approves.
    """
    return "approve" if state.get("approved") else "reject"


def _fail_run_node(recorder):
    """Build the node that records a stage failure and stamps the run on the event."""

    def fail_run(state: GraphState) -> dict:
        failure: RunFailure = state["failure"]
        coding_run_id = state.get("coding_run_id")
        recorder.fail(coding_run_id, failed_stage=failure.failed_stage, reason=failure.reason)
        stamped_failure = failure.model_copy(update={"coding_run_id": coding_run_id})
        emit(stamped_failure)
        return {"failure": stamped_failure, "trace": ["fail_run"]}

    return fail_run


def _default_workspace_factory(checkout_root):
    return LocalGitWorkspace(checkout_root)


def _default_publisher_factory(_repository_id):
    return NullPatchPublisher()


def build_graph(
    *,
    classifier_llm,
    retriever,
    llm,
    planner_llm,
    generator,
    reviewer,
    run_recorder=None,
    workspace_factory=None,
    publisher_factory=None,
    checkpointer=None,
    max_revision_attempts=None,
):
    """Compile the unified intent-routed graph.

    ``checkpointer`` is the durable graph-state store. Production passes the
    process-wide ``PostgresSaver`` (its connection pool is the singleton, opened
    once in the FastAPI lifespan); compiling the graph itself is an in-memory
    wiring step done per request. Tests omit it and get an ephemeral
    ``MemorySaver``.
    """
    recorder = run_recorder or NullRunRecorder()
    workspaces = workspace_factory or _default_workspace_factory
    publishers = publisher_factory or _default_publisher_factory
    graph = StateGraph(GraphState)
    graph.add_node("classify", _classify_node(classifier_llm))
    graph.add_node("plan", build_plan_node(planner_llm, recorder))
    graph.add_node("gather_evidence", build_gather_evidence_node(retriever, recorder))
    graph.add_node("prepare_branch", build_prepare_branch_node(workspaces, recorder), destinations=("generate_tests", "fail_run"))
    graph.add_node("generate_tests", build_generate_tests_node(generator), destinations=("build_patch", "fail_run"))
    graph.add_node("build_patch", build_build_patch_node(workspaces, recorder), destinations=("review_patch", "fail_run"))
    graph.add_node("review_patch", build_review_patch_node(reviewer, recorder))
    graph.add_node(
        "review_gate", build_review_gate_node(max_revision_attempts=max_revision_attempts), destinations=("await_decision", "revise_tests", "fail_run")
    )
    graph.add_node("await_decision", build_await_decision_node())
    graph.add_node("approve_patch", build_approve_patch_node(publishers, workspaces, recorder), destinations=(END, "fail_run"))
    graph.add_node("discard_patch", build_discard_patch_node(workspaces, recorder))
    graph.add_node("revise_tests", build_revise_tests_node(generator), destinations=("build_patch", "fail_run"))
    graph.add_node("fail_run", _fail_run_node(recorder))
    graph.add_node("retrieve", build_retrieve_node(retriever))
    graph.add_node("generate", build_generate_node(llm))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_intent, {"test_generation": "plan", "repository_question": "retrieve"})
    graph.add_conditional_edges("plan", _route_after_plan, {"failed": "fail_run", "planned": "gather_evidence"})
    graph.add_edge("gather_evidence", "prepare_branch")
    graph.add_edge("review_patch", "review_gate")
    graph.add_conditional_edges("await_decision", _route_after_decision, {"approve": "approve_patch", "reject": "discard_patch"})
    graph.add_edge("discard_patch", END)
    graph.add_edge("fail_run", END)
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())
