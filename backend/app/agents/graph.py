"""The unified intent-routed LangGraph for repository sessions.

A single ``StateGraph`` over one shared state object infers the Request Intent in
a ``classify`` node and routes to one of two branches: ``repository_question``
(retrieval-grounded answer) or ``code_generation`` (a bounded plan/retrieve run).
The graph is compiled with a checkpointer (the durable ``PostgresSaver`` in
production, an ephemeral ``MemorySaver`` in tests) so a per-run ``thread_id``
carries in-flight state, leaving room for later human-in-the-loop interrupts
without re-architecting.
"""

import operator
import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.agents.fallback import model_label, with_provider_fallback
from app.agents.nodes.code_generation import (
    build_approval_router,
    build_approve_patch_node,
    build_await_decision_node,
    build_discard_patch_node,
    build_gather_documents_node,
    build_gather_documents_router,
    build_generate_code_node,
    build_generate_router,
    build_report_no_changes_node,
    build_review_patch_node,
    build_review_router,
)
from app.agents.nodes.planner import build_plan_node
from app.agents.nodes.repository_question import QuestionShape, build_analyzing_node, build_decompose_parallel_node, build_simple_rag_node
from app.schemas import Citation, PatchResult, RetrievalRequest, ReviewResult, RunApproved, RunFailure, RunNoChanges, RunRejected, Stage
from app.streaming import emit

Intent = Literal["repository_question", "code_generation"]


class Classification(BaseModel):
    """Structured output of the ``classify`` node."""

    intent: Intent = Field(description="Route the user's request to either a read-only repository question or a code-generation coding run.")


class SharedState(TypedDict):
    """The conversational/identity spine every node reads, whatever the branch."""

    # The LangChain-native message spine: recent Session History plus the current
    # turn, reduced with ``add_messages`` (so it starts empty and accumulates).
    # ``classify`` reads it so follow-ups ("now write tests for that") route on
    # conversational context, not the bare question. ``question`` stays as the plain
    # retrieval/planning query string.
    messages: Annotated[list, add_messages]
    question: str
    repository_id: uuid.UUID
    repository_session_id: uuid.UUID
    intent: Intent | None
    # The terminal failure any stage may fold onto state for the single failure sink.
    failure: RunFailure | None
    # Append-only breadcrumb of visited nodes; starts empty and accumulates.
    trace: Annotated[list[str], operator.add]


class RepositoryQuestionState(TypedDict):
    """The ``repository_question`` branch's private working set (analyzing → strategy)."""

    # The Question Shape inferred by ``analyzing``, selecting the retrieval strategy.
    question_shape: QuestionShape | None
    documents: list | None
    answer: str | None
    citations: list[Citation] | None


class CodeGenerationState(TypedDict):
    """The ``code_generation`` pipeline's private working set (plan → … → approve/discard)."""

    coding_run_id: uuid.UUID | None
    checkout_root: str | None
    indexed_commit_sha: str | None
    retrieval_requests: list[RetrievalRequest] | None
    source_documents: list | None
    test_documents: list | None
    candidate_hints: list[str] | None
    generation_branch: str | None
    generated_files: list | None
    external_references: list | None
    diff: str | None
    patch_result: PatchResult | None
    review_result: ReviewResult | None
    # Count of spent Generation Retries; ``None``/absent means none spent yet. The
    # spend/limit arithmetic lives in ``app.services.coding_runs.generation_retries``.
    generation_retries: int | None
    # The owner's human-in-the-loop decision on an accepted patch, supplied by resuming
    # the suspended graph, and the terminal outcome when that decision is a rejection.
    approved: bool | None
    human_feedback: str | None
    rejection_result: RunRejected | None
    approval_result: RunApproved | None
    # The terminal outcome when the generator proposes no test changes across all attempts.
    no_changes_result: RunNoChanges | None


class GraphState(SharedState, RepositoryQuestionState, CodeGenerationState):
    """The single state threaded through every node.

    Composed from the shared spine plus the two branches' private working sets, so the
    schema reads as three small named groups rather than one flat wall of fields. The
    keys still collapse into one channel namespace on the compiled graph — this is an
    organizational split, not a subgraph boundary.
    """


def _classify_node(classifier_llm, fallback_llm):
    """Build the classify node; uncertain classification falls back to read-only."""
    structured = with_provider_fallback(
        classifier_llm,
        fallback_llm,
        lambda model: model.with_structured_output(Classification),
        primary_label=model_label(classifier_llm),
        fallback_label=model_label(fallback_llm),
    )

    def classify(state: GraphState) -> dict:
        emit(Stage(stage="classifying"))
        # Read recent Session History when present; fall back to the bare question.
        messages = state.get("messages") or [HumanMessage(content=state["question"])]
        result = structured.invoke(messages)
        intent: Intent = result.intent if result else "repository_question"
        return {"intent": intent, "trace": ["classify"]}

    return classify


def _route_intent(state: GraphState) -> Intent:
    """Route off the ``classify`` verdict, defaulting to the read-only question branch."""
    return state.get("intent", "repository_question")


def _route_question_shape(state: GraphState) -> QuestionShape:
    """Route each Question Shape to its strategy node, defaulting to the read-only ``simple`` shape.

    ``simple`` (and the uncertain fallback) takes ``simple_rag``; ``independent`` takes
    ``decompose_parallel``. ``chained`` is recognized but routes to ``simple_rag`` as a
    placeholder until its own strategy node lands.
    """
    return state.get("question_shape", "simple")


def _route_after_plan(state: GraphState) -> Literal["failed", "planned"]:
    """Route a planning-stage failure to the sink, otherwise on to documents gathering."""
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


def build_graph(
    *,
    classifier_llm,
    default_fallback_llm,
    retriever,
    llm,
    planner_llm,
    code_generator,
    code_reviewer,
    run_recorder,
    workspace_factory,
    publisher_factory,
    checkpointer,
    review_policy,
):
    """Compile the unified intent-routed graph.

    Every runtime adapter is an explicit, required input: ``run_recorder``
    (Coding Run persistence), ``workspace_factory`` (checkout workspace
    behavior), ``publisher_factory`` (Test Patch publishing), and
    ``checkpointer`` (the durable graph-state store). None has an omission-based
    fallback — leaving one out raises here, at the graph-construction boundary,
    rather than silently compiling a graph with no-op recording, no-op
    publishing, local-Git workspace, or in-memory checkpointing.

    The application composition root chooses the production adapters: the
    process-wide ``PostgresSaver`` (its connection pool opened once in the
    FastAPI lifespan; only the in-memory graph wiring is rebuilt per request),
    the ``CodingRunRecorder``, the local checkout workspace factory, and the Git
    patch publisher. Tests deliberately choose their null, fake, local, or
    in-memory adapters according to the behavior under test (ADR-0002).

    The Patch Review policy is likewise resolved once and required here: the same
    ``review_policy`` (the pass threshold and the Generation Retries limit) is
    threaded into both ``review_patch`` and its post-review router, so a Test Patch
    is scored, retried, escalated, or reported as already covered under one coherent
    configuration rather than each consumer reading global settings on its own.
    """
    recorder = run_recorder
    workspaces = workspace_factory
    publishers = publisher_factory
    graph = StateGraph(GraphState)
    graph.add_node("classify", _classify_node(classifier_llm, default_fallback_llm))
    graph.add_node("plan", build_plan_node(planner_llm, recorder, fallback_llm=default_fallback_llm))
    graph.add_node("gather_documents", build_gather_documents_node(retriever, recorder))
    graph.add_node("generate_code", build_generate_code_node(code_generator, workspaces, recorder))
    graph.add_node("review_patch", build_review_patch_node(code_reviewer, recorder, policy=review_policy))
    graph.add_node("await_decision", build_await_decision_node())
    graph.add_node("approve_patch", build_approve_patch_node(publishers, workspaces, recorder))
    graph.add_node("discard_patch", build_discard_patch_node(workspaces, recorder))
    graph.add_node("report_no_changes", build_report_no_changes_node(recorder))
    graph.add_node("fail_run", _fail_run_node(recorder))
    graph.add_node("analyzing", build_analyzing_node(classifier_llm, default_fallback_llm))
    graph.add_node("simple_rag", build_simple_rag_node(retriever, llm, default_fallback_llm))
    graph.add_node("decompose_parallel", build_decompose_parallel_node(retriever, llm, default_fallback_llm))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route_intent, {"code_generation": "plan", "repository_question": "analyzing"})
    graph.add_conditional_edges(
        "analyzing", _route_question_shape, {"simple": "simple_rag", "independent": "decompose_parallel", "chained": "simple_rag"}
    )
    graph.add_conditional_edges("plan", _route_after_plan, {"failed": "fail_run", "planned": "gather_documents"})
    graph.add_conditional_edges("gather_documents", build_gather_documents_router(), {"gathered": "generate_code", "failed": "fail_run"})
    graph.add_conditional_edges("generate_code", build_generate_router(), {"review": "review_patch", "failed": "fail_run"})
    graph.add_conditional_edges(
        "review_patch",
        build_review_router(review_policy),
        {"revise": "generate_code", "escalate": "await_decision", "already_covered": "report_no_changes", "failed": "fail_run"},
    )
    graph.add_conditional_edges("await_decision", _route_after_decision, {"approve": "approve_patch", "reject": "discard_patch"})
    graph.add_conditional_edges("approve_patch", build_approval_router(), {"approved": END, "failed": "fail_run"})
    graph.add_edge("discard_patch", END)
    graph.add_edge("report_no_changes", END)
    graph.add_edge("fail_run", END)
    graph.add_edge("simple_rag", END)
    graph.add_edge("decompose_parallel", END)

    return graph.compile(checkpointer=checkpointer)
