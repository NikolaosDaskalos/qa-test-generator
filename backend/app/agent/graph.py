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

from app.agent.planner import build_plan_node
from app.agent.repository_question import build_generate_node, build_retrieve_node
from app.agent.run_recorder import NullRunRecorder
from app.agent.stream import emit
from app.agent.test_generation import build_gather_evidence_node
from app.enums.coding_run import CodingRunStatus
from app.schemas.agent_stream import Citation, RunFailure, RunStarted, Stage
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
    evidence: list
    answer: str
    citations: list[Citation]
    research_intents: list[ResearchIntent]
    source_evidence: list
    test_evidence: list
    candidate_hints: list[str]
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


def _persist_run_node(recorder):
    """Build the test-branch entry node that persists a queued run and enters planning."""

    def persist_run(state: GraphState, config) -> dict:
        thread_id = config["configurable"]["thread_id"]
        coding_run_id = recorder.start(
            thread_id=thread_id,
            repository_session_id=state.get("repository_session_id"),
        )
        recorder.advance(coding_run_id, CodingRunStatus.planning)
        emit(RunStarted(coding_run_id=coding_run_id))
        emit(Stage(stage="planning"))
        return {"coding_run_id": coding_run_id, "trace": ["persist_run"]}

    return persist_run


def _begin_retrieving_node(recorder):
    """Build the node that advances a run into the retrieving stage."""

    def begin_retrieving(state: GraphState) -> dict:
        recorder.advance(state["coding_run_id"], CodingRunStatus.retrieving)
        emit(Stage(stage="retrieving"))
        return {"trace": ["begin_retrieving"]}

    return begin_retrieving


def _fail_run_node(recorder):
    """Build the node that records a stage failure and stamps the run on the event."""

    def fail_run(state: GraphState) -> dict:
        failure: RunFailure = state["failure"]
        coding_run_id = state.get("coding_run_id")
        recorder.fail(coding_run_id, failed_stage=failure.failed_stage, reason=failure.reason)
        return {"failure": failure.model_copy(update={"coding_run_id": coding_run_id}), "trace": ["fail_run"]}

    return fail_run


def build_graph(*, classifier_llm, retriever, llm, planner_llm, run_recorder=None, checkpointer=None):
    """Compile the unified intent-routed graph.

    ``checkpointer`` is the durable graph-state store. Production passes the
    process-wide ``PostgresSaver`` (its connection pool is the singleton, opened
    once in the FastAPI lifespan); compiling the graph itself is an in-memory
    wiring step done per request. Tests omit it and get an ephemeral
    ``MemorySaver``.
    """
    recorder = run_recorder or NullRunRecorder()
    graph = StateGraph(GraphState)
    graph.add_node("classify", _classify_node(classifier_llm))
    graph.add_node("persist_run", _persist_run_node(recorder))
    graph.add_node("plan", build_plan_node(planner_llm))
    graph.add_node("begin_retrieving", _begin_retrieving_node(recorder))
    graph.add_node("gather_evidence", build_gather_evidence_node(retriever))
    graph.add_node("fail_run", _fail_run_node(recorder))
    graph.add_node("retrieve", build_retrieve_node(retriever))
    graph.add_node("generate", build_generate_node(llm))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_intent, {"test_generation": "persist_run", "repository_question": "retrieve"})
    graph.add_edge("persist_run", "plan")
    graph.add_conditional_edges("plan", _route_after_plan, {"failed": "fail_run", "planned": "begin_retrieving"})
    graph.add_edge("begin_retrieving", "gather_evidence")
    graph.add_edge("gather_evidence", END)
    graph.add_edge("fail_run", END)
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())
