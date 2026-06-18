"""The ``test_generation`` generic retrieve node.

This node executes the planner's Research Intents under the session's Repository
identity. Each intent's untrusted candidate paths are confined to the checkout
(unsafe ones dropped) before any survive into state as validated retrieval hints.
Retrieved Repository Evidence is partitioned by the intent's tag into separate
``source_evidence`` (what's implemented) and ``test_evidence`` (what's already
tested), which are kept apart on the shared state.
"""

import logging
from typing import Literal

from langgraph.graph import END
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.services.coding_runs.decision_finalizer import DecisionFinalizer
from app.services.coding_runs.evidence_partitioner import EvidencePartitioner, EvidencePartitionRequest
from app.services.coding_runs.patch_builder import PatchBuilder, PatchBuildRequest
from app.services.coding_runs.revision_budget import RevisionBudget
from app.streaming.agent_stream import emit
from app.services.coding_runs.test_file_validation import verify_test_file_boundary
from app.enums.coding_run import CodingRunStage
from app.schemas.agent_stream import ReviewResult, RunFailure, Stage

logger = logging.getLogger(__name__)

# User-safe reasons for a generating-stage failure; never raw exception text.
BRANCH_PREPARATION_FAILED = "Could not prepare a clean branch to generate tests on."
GENERATION_FAILED = "The test generator could not produce a valid proposal."
REVISION_FAILED = "The test generator could not revise its proposal."
# User-safe reasons for a reviewing-stage failure; never raw exception text.
REVIEW_FAILED = "The patch reviewer could not complete its assessment."
# The prompt the human-in-the-loop interrupt surfaces while awaiting the owner's decision.
AWAITING_DECISION_MESSAGE = "Review the generated Test Patch and approve or reject it."


def _continue_to(node: str, update: dict) -> Command:
    return Command(update=update, goto=node)


def _fail_with(failure: RunFailure, trace: str) -> Command:
    return Command(update={"failure": failure, "trace": [trace]}, goto="fail_run")


def build_gather_evidence_node(retriever, recorder):
    """Build the generic retrieve node that partitions evidence source vs. test.

    Gathering evidence first advances the run into the retrieving stage and emits
    the retrieving marker, then partitions Repository Evidence as before.
    """

    partitioner = EvidencePartitioner(retriever)

    def gather_evidence(state) -> dict:
        recorder.begin_retrieving(state["coding_run_id"])
        emit(Stage(stage="retrieving"))
        partition = partitioner.partition(
            EvidencePartitionRequest(
                research_intents=state.get("research_intents") or [], repository_id=state["repository_id"], checkout_root=state.get("checkout_root")
            )
        )
        return {
            "source_evidence": partition.source_evidence,
            "test_evidence": partition.test_evidence,
            "candidate_hints": partition.candidate_hints,
            "trace": ["gather_evidence"],
        }

    return gather_evidence


def build_prepare_branch_node(workspace_factory, recorder):
    """Build the node that restores a clean generation branch at the indexed commit.

    The backend — never the model — restores the shared checkout to the
    Repository's indexed commit on a uniquely named, non-default temporary branch
    before any generation. A Git failure here is a generating-stage Run Failure.
    """

    def prepare_branch(state) -> dict:
        recorder.begin_generating(state["coding_run_id"])
        try:
            workspace = workspace_factory(state.get("checkout_root"))
            branch = workspace.prepare_branch(state.get("indexed_commit_sha"))
        except Exception:
            logger.exception("Generation branch preparation failed")
            return _fail_with(RunFailure(failed_stage=CodingRunStage.generating, reason=BRANCH_PREPARATION_FAILED), "prepare_branch")
        return _continue_to("generate_tests", {"generation_branch": branch, "trace": ["prepare_branch"]})

    return prepare_branch


def build_generate_tests_node(generator):
    """Build the bounded generator node that proposes complete Test File contents.

    The generator may call only the bounded ``web_search`` tool — no shell or
    filesystem access — and returns structured complete-file proposals plus the
    External References it consulted, kept separate from Repository Evidence.
    """

    def generate_tests(state) -> dict:
        emit(Stage(stage="generating"))
        try:
            proposal = generator.generate(
                task=state["question"], source_evidence=state.get("source_evidence") or [], test_evidence=state.get("test_evidence") or []
            )
        except Exception:
            logger.exception("Test generation failed")
            return _fail_with(RunFailure(failed_stage=CodingRunStage.generating, reason=GENERATION_FAILED), "generate_tests")
        return _continue_to(
            "build_patch", {"generated_files": proposal.generated_files, "external_references": proposal.external_references, "trace": ["generate_tests"]}
        )

    return generate_tests


def build_revise_tests_node(generator):
    """Build the node that performs one Revision Attempt against a below-threshold review.

    The generator is handed the original task, partitioned Repository Evidence, its
    own prior complete-file proposal, the canonical diff that was reviewed, and the
    reviewer's findings, and replaces the proposal. The revised files flow back
    through the same write/validation/review path as initial generation; a generator
    failure here is a generating-stage Run Failure. One unit of the Revision Budget is
    spent so the post-review router admits only as many revisions as the budget allows
    before escalating to human review.
    """

    def revise_tests(state) -> dict:
        emit(Stage(stage="revising"))
        review: ReviewResult | None = state.get("review_result")
        findings = list(review.findings) if review is not None else []
        try:
            proposal = generator.revise(
                task=state["question"],
                source_evidence=state.get("source_evidence") or [],
                test_evidence=state.get("test_evidence") or [],
                prior_files=state.get("generated_files") or [],
                diff=state.get("diff") or "",
                findings=findings,
            )
        except Exception:
            logger.exception("Test revision failed")
            return _fail_with(RunFailure(failed_stage=CodingRunStage.generating, reason=REVISION_FAILED), "revise_tests")
        budget = RevisionBudget.from_state(state).spend()
        return _continue_to(
            "build_patch",
            {
                "generated_files": proposal.generated_files,
                "external_references": proposal.external_references or state.get("external_references") or [],
                **budget.state_update(),
                "trace": ["revise_tests"],
            },
        )

    return revise_tests


def build_build_patch_node(workspace_factory, recorder):
    """Build the node that validates, writes, and derives the canonical Test Patch.

    Each proposed path is validated before any write; an unsafe path, a non-Python
    file, or application code is a generating-stage Run Failure. Validated files are
    written and the displayed diff is obtained from Git, then the Coding Run
    persists the proposals, External References, and canonical diff.
    """

    builder = PatchBuilder(workspace_factory=workspace_factory, recorder=recorder)

    def build_patch(state) -> dict:
        outcome = builder.build(
            PatchBuildRequest(
                generated_files=state.get("generated_files") or [],
                checkout_root=state.get("checkout_root"),
                is_revision_attempt=RevisionBudget.from_state(state).is_revision_attempt,
                generation_branch=state.get("generation_branch"),
                coding_run_id=state.get("coding_run_id"),
                external_references=state.get("external_references") or [],
            )
        )
        if outcome.failure is not None:
            return _fail_with(outcome.failure, "build_patch")
        patch_result = outcome.patch_result
        return _continue_to(
            "review_patch", {"patch_result": patch_result, "diff": patch_result.diff, "generated_files": patch_result.generated_files, "trace": ["build_patch"]}
        )

    return build_patch


def _escalates_to_owner(review: ReviewResult | None, state, max_revision_attempts: int | None) -> bool:
    """Whether the post-review path escalates this patch to the owner's decision.

    An accepted patch escalates; a below-threshold patch escalates only once its
    Revision Budget is spent (otherwise it is revised). A reviewing-stage failure
    (no review on state) escalates to neither — it routes to the failure sink.
    """
    if review is None:
        return False
    if not review.accepted and RevisionBudget.from_state(state, limit=max_revision_attempts).can_spend:
        return False
    return True


def build_review_patch_node(reviewer, recorder, *, threshold: int | None = None, max_revision_attempts: int | None = None):
    """Build the node that statically reviews a generated Test Patch before approval.

    Review is evidence-based static assessment only: the reviewer never executes
    the generated tests, installs dependencies, or implies runtime correctness. The
    reviewer returns a quality ``score`` (0–10); the backend — not the model — owns
    the pass decision, accepting the patch when ``score >= threshold`` (the
    configurable ``REVIEW_PASS_THRESHOLD``). The backend independently re-verifies
    the Test File boundary, so a patch that escapes Test-File scope is rejected even
    when its score passes. The decision is persisted (accepted → awaiting approval,
    rejected → changes requested) and surfaced as a ``ReviewResult`` carrying the
    score, the threshold it was judged against, the findings, and the assessed diff.

    The node returns plain state — never a ``Command`` — leaving post-review routing
    to an explicit conditional edge (see ``build_review_router``). It does emit the
    terminal ``ReviewResult`` whenever the run escalates to the owner (an accepted
    patch, or a below-threshold one with the Revision Budget — bounded by
    ``max_revision_attempts`` — exhausted), so the escalated patch surfaces its score
    on the Agent Stream; a patch bound for one more Revision Attempt stays quiet until
    its re-review.
    """

    pass_threshold = settings.REVIEW_PASS_THRESHOLD if threshold is None else threshold

    def review_patch(state) -> dict:
        coding_run_id = state.get("coding_run_id")
        recorder.begin_reviewing(coding_run_id)
        # A second pass over this node is the review of a Revision Attempt; surface it
        # as a distinct stage marker so the Agent Stream tells the two reviews apart.
        emit(Stage(stage="re_reviewing" if RevisionBudget.from_state(state).is_revision_attempt else "reviewing"))
        diff = state.get("diff") or ""
        generated_files = state.get("generated_files") or []

        # The reviewer is an LLM/tool loop: a failure in its model call, structured
        # response parsing, or web_search loop is a reviewing-stage Run Failure, not
        # an escaping exception that would leave the run stuck in ``reviewing``.
        try:
            review = reviewer.review(
                task=state["question"],
                source_evidence=state.get("source_evidence") or [],
                test_evidence=state.get("test_evidence") or [],
                generated_files=generated_files,
                diff=diff,
            )
        except Exception:
            logger.exception("Patch review failed")
            return {"failure": RunFailure(failed_stage=CodingRunStage.reviewing, reason=REVIEW_FAILED), "trace": ["review_patch"]}
        # The reviewer only scores; the backend owns the pass bar.
        score = review.score
        findings = list(review.findings)
        accepted = score >= pass_threshold

        # The score is never the sole gate: the backend independently re-verifies that
        # every proposal stays within the Test File boundary, overriding a passing score.
        boundary_finding = verify_test_file_boundary(state.get("checkout_root"), generated_files)
        if boundary_finding is not None:
            accepted = False
            findings = [*findings, boundary_finding]

        recorder.record_review(coding_run_id, accepted=accepted, findings=findings)
        review_result = ReviewResult(coding_run_id=coding_run_id, accepted=accepted, score=score, threshold=pass_threshold, findings=findings, diff=diff)
        # The terminal ReviewResult rides the stream only when the run escalates to the
        # owner; a patch bound for one more Revision Attempt stays quiet until re-review.
        if _escalates_to_owner(review_result, state, max_revision_attempts):
            emit(review_result)
        return {"review_result": review_result, "trace": ["review_patch"]}

    return review_patch


def build_review_router(max_revision_attempts: int | None = None):
    """Build the post-review router that drives the conditional edge off ``review_patch``.

    Reading only the verdict ``review_patch`` wrote to state, it reproduces the three
    outcomes the old ``review_gate`` owned: a reviewing-stage Run Failure routes to
    the failure sink; a below-threshold patch with Revision Budget remaining routes
    back to one more ``revise_tests``; an accepted patch, or a below-threshold one
    whose budget is exhausted, routes to the owner's human decision. Exhausting the
    budget escalates — it never fails. The router has no side effects; ``review_patch``
    already emitted the terminal ``ReviewResult`` on the escalation path.
    """

    def route_after_review(state) -> Literal["revise", "escalate", "failed"]:
        if state.get("failure") is not None:
            return "failed"
        if _escalates_to_owner(state.get("review_result"), state, max_revision_attempts):
            return "escalate"
        return "revise"

    return route_after_review


def build_await_decision_node():
    """Build the human-in-the-loop node that suspends a run for the owner's decision.

    The post-review router routes here both for an accepted Patch Review and for a
    below-threshold patch whose Revision Budget is exhausted, so the graph pauses via
    ``interrupt`` surfacing the Coding Run, the assessed canonical diff, the review
    ``score`` and ``threshold``, whether the backend accepted it, and the findings —
    enough for the owner to judge an escalated below-threshold patch. The graph is
    resumed with the owner's decision payload (``{"approved": bool, "feedback": str}``),
    which is folded onto state so the post-decision router can approve or reject. No
    work touches the checkout here; discarding is the rejected branch's concern.
    """

    def await_decision(state) -> dict:
        review: ReviewResult | None = state.get("review_result")
        decision = interrupt(
            {
                "coding_run_id": state.get("coding_run_id"),
                "diff": state.get("diff") or "",
                "score": review.score if review is not None else None,
                "threshold": review.threshold if review is not None else None,
                "accepted": review.accepted if review is not None else None,
                "findings": [finding.model_dump() for finding in (review.findings if review is not None else [])],
                "message": AWAITING_DECISION_MESSAGE,
            }
        )
        approved = bool(decision.get("approved", False)) if isinstance(decision, dict) else bool(decision)
        feedback = decision.get("feedback", "") if isinstance(decision, dict) else ""
        return {"approved": approved, "human_feedback": feedback, "trace": ["await_decision"]}

    return await_decision


def build_discard_patch_node(workspace_factory, recorder):
    """Build the thin adapter that discards a rejected Test Patch and records the rejection.

    The node unpacks state, delegates the discard-then-reject orchestration to the
    deep ``DecisionFinalizer`` (restore the checkout, remove the temporary branch with
    local Git only, persist the rejection while preserving the review record), emits
    the returned terminal ``RunRejected``, and folds it onto state. The finalizer holds
    no wire knowledge; emission stays at the node.
    """

    finalizer = DecisionFinalizer(recorder=recorder)

    def discard_patch(state) -> dict:
        review: ReviewResult | None = state.get("review_result")
        rejection = finalizer.discard(
            workspace=workspace_factory(state.get("checkout_root")),
            coding_run_id=state.get("coding_run_id"),
            generation_branch=state.get("generation_branch"),
            diff=state.get("diff") or "",
            indexed_commit_sha=state.get("indexed_commit_sha"),
            findings=list(review.findings) if review is not None else [],
        )
        emit(rejection)
        return {"rejection_result": rejection, "trace": ["discard_patch"]}

    return discard_patch


def build_approve_patch_node(publisher_factory, workspace_factory, recorder):
    """Build the thin adapter that finalizes an owner-approved Test Patch.

    The node unpacks state, builds the publisher and workspace, delegates the
    commit → push → record-approved → restore-checkout orchestration to the deep
    ``DecisionFinalizer``, then emits the returned terminal and folds it onto state. A
    ``git_commit`` / ``git_push`` Run Failure short-circuits the run; a ``RunApproved``
    ends it. Emission stays at the node; the finalizer holds no wire knowledge.
    """

    finalizer = DecisionFinalizer(recorder=recorder)

    def approve_patch(state) -> dict:
        outcome = finalizer.approve(
            publisher=publisher_factory(state["repository_id"]),
            workspace=workspace_factory(state.get("checkout_root")),
            coding_run_id=state.get("coding_run_id"),
            generation_branch=state.get("generation_branch"),
            diff=state.get("diff") or "",
            indexed_commit_sha=state.get("indexed_commit_sha"),
        )
        emit(outcome)
        if isinstance(outcome, RunFailure):
            return _fail_with(outcome, "approve_patch")
        return Command(update={"approval_result": outcome, "trace": ["approve_patch"]}, goto=END)

    return approve_patch
