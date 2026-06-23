"""Nodes for the ``code_generation`` workflow.

This node executes the planner's Retrieval Requests under the session's Repository
identity. Each request's untrusted candidate paths are confined to the checkout
(unsafe ones dropped) before any survive into state as validated retrieval hints.
Retrieved Repository Documents are partitioned by document type into separate
``source_documents`` (what's implemented) and ``test_documents`` (what's already
tested), which are kept apart on the shared state.
"""

import logging
from typing import Literal

from langgraph.types import interrupt

from app.agents.nodes.failures import fail_state
from app.enums import CodingRunStage
from app.schemas import ReviewFinding, ReviewResult, RunFailure, RunNoChanges, Stage
from app.services.coding_runs.decision_finalizer import DecisionFinalizer
from app.services.coding_runs.generation_retries import can_retry_generation, is_generation_retry, spend_generation_retry
from app.services.coding_runs.review_policy import ReviewPolicy
from app.services.coding_runs.patch_builder import PatchBuilder, PatchBuildRequest
from app.services.coding_runs.repository_document_partitioner import RepositoryDocumentPartitioner, RepositoryDocumentPartitionRequest
from app.services.coding_runs.test_file_validation import verify_test_file_boundary
from app.streaming import emit

logger = logging.getLogger(__name__)

# User-safe reason for a retrieving-stage failure when no checkout context is present.
MISSING_CHECKOUT = "Could not gather repository documents without a prepared checkout."
# User-safe reasons for a generating-stage failure; never raw exception text.
BRANCH_PREPARATION_FAILED = "Could not prepare a clean branch to generate tests on."
GENERATION_FAILED = "The code generator could not produce a valid proposal."
REVISION_FAILED = "The code generator could not revise its proposal."
# User-safe reasons for a reviewing-stage failure; never raw exception text.
REVIEW_FAILED = "The Code Reviewer could not complete its assessment."
# The prompt the human-in-the-loop interrupt surfaces while awaiting the owner's decision.
AWAITING_DECISION_MESSAGE = "Review the generated Test Patch and approve or reject it."
# An empty proposal scores zero deterministically; the backend, not the model, owns this.
EMPTY_PATCH_SCORE = 0
EMPTY_PATCH_FINDING = ReviewFinding(category="coverage", detail="The generator proposed no test changes.")
# Ready-to-show copy for a run that proposed no test changes across every attempt.
NO_CHANGES_MESSAGE = "The existing tests already cover all the requested cases, so no new tests were generated."


def build_gather_documents_node(retriever, recorder):
    """Build the generic retrieve node that partitions documents source vs. test.

    Gathering documents first advances the run into the retrieving stage and emits
    the retrieving marker, then partitions Repository Documents as before.
    """

    partitioner = RepositoryDocumentPartitioner(retriever)

    def gather_documents(state) -> dict:
        recorder.begin_retrieving(state["coding_run_id"])
        emit(Stage(stage="retrieving"))
        # Candidate Repository paths are untrusted hints that must be confined against the
        # checkout before entering agent context; a missing checkout cannot silently drop
        # them, so the Code Generation path fails explicitly at this boundary.
        checkout_root = state.get("checkout_root")
        if not checkout_root:
            return fail_state(RunFailure(failed_stage=CodingRunStage.retrieving, reason=MISSING_CHECKOUT), trace="gather_documents")
        partition = partitioner.partition(
            RepositoryDocumentPartitionRequest(
                retrieval_requests=state.get("retrieval_requests") or [], repository_id=state["repository_id"], checkout_root=checkout_root
            )
        )
        return {
            "source_documents": partition.source_documents,
            "test_documents": partition.test_documents,
            "candidate_hints": partition.candidate_hints,
            "trace": ["gather_documents"],
        }

    return gather_documents


def build_gather_documents_router():
    """Build the router that drives the conditional edge off ``gather_documents``.

    Reading only the state the node wrote, it routes a retrieving-stage failure (a
    missing checkout) to the failure sink and an otherwise-partitioned set of
    Repository Documents on to generation.
    """

    def route_after_gather(state) -> Literal["gathered", "failed"]:
        return "failed" if state.get("failure") is not None else "gathered"

    return route_after_gather


def _generating_failure(reason: str) -> dict:
    """Plain generating-stage failure state for the merged node's exception arms."""
    return fail_state(RunFailure(failed_stage=CodingRunStage.generating, reason=reason), trace="generate_code")


def build_generate_code_node(code_generator, workspace_factory, recorder):
    """Build the single node that runs the whole generating stage end-to-end.

    The node distinguishes its two passes by whether a prior ``review_result`` is on
    state — absent on the first pass (straight from documents gathering), present
    whenever the post-review router routes a below-threshold patch back here. On the
    first pass it advances the run into generating, restores a clean generation branch
    at the indexed commit (the backend — never the model — owns this), and calls the
    Code Generator's initial generation. On a retry pass it skips branch preparation (the
    branch already exists), calls the Code Generator's revision with the prior proposal,
    the reviewed canonical diff, and the Code Reviewer's findings, and spends one
    Generation Retry. The Code Generator may call only the
    bounded ``web_search`` tool — no shell or filesystem access.

    Either pass then validates, writes, and derives the canonical Test Patch through the
    deep ``PatchBuilder`` (a revision resets the prior patch first via the now-spent
    ``is_generation_retry`` signal). The node returns plain state — never a ``Command`` —
    leaving routing to ``build_generate_router``. Any generating-stage failure (branch
    preparation, generation, revision, or patch validation/build) is folded onto state
    as a user-safe ``RunFailure`` instead of escaping.
    """

    builder = PatchBuilder(workspace_factory=workspace_factory, recorder=recorder)

    def generate_code(state) -> dict:
        review: ReviewResult | None = state.get("review_result")
        # A prior review on state means the router routed a below-threshold patch back
        # here for one more Generation Retry; its absence is the first generation pass.
        is_retry = review is not None

        if is_retry:
            emit(Stage(stage="revising"))
            try:
                proposal = code_generator.revise(
                    task=state["question"],
                    source_documents=state.get("source_documents") or [],
                    test_documents=state.get("test_documents") or [],
                    prior_files=state.get("generated_files") or [],
                    diff=state.get("diff") or "",
                    findings=list(review.findings),
                )
            except Exception:
                logger.exception("Test revision failed")
                return _generating_failure(REVISION_FAILED)
            generation_branch = state.get("generation_branch")
            external_references = proposal.external_references or state.get("external_references") or []
            budget_update = spend_generation_retry(state)
        else:
            recorder.begin_generating(state["coding_run_id"])
            try:
                workspace = workspace_factory(state.get("checkout_root"))
                generation_branch = workspace.prepare_branch(state.get("indexed_commit_sha"))
            except Exception:
                logger.exception("Generation branch preparation failed")
                return _generating_failure(BRANCH_PREPARATION_FAILED)
            emit(Stage(stage="generating"))
            try:
                proposal = code_generator.generate(
                    task=state["question"], source_documents=state.get("source_documents") or [], test_documents=state.get("test_documents") or []
                )
            except Exception:
                logger.exception("Code generation failed")
                return _generating_failure(GENERATION_FAILED)
            external_references = proposal.external_references
            budget_update = {}

        outcome = builder.build(
            PatchBuildRequest(
                generated_files=proposal.generated_files,
                checkout_root=state.get("checkout_root"),
                is_generation_retry=is_retry,
                generation_branch=generation_branch,
                coding_run_id=state.get("coding_run_id"),
                external_references=external_references,
            )
        )
        if outcome.failure is not None:
            return fail_state(outcome.failure, trace="generate_code")
        patch_result = outcome.patch_result
        return {
            "generation_branch": generation_branch,
            "generated_files": patch_result.generated_files,
            "external_references": patch_result.external_references,
            "patch_result": patch_result,
            "diff": patch_result.diff,
            **budget_update,
            "trace": ["generate_code"],
        }

    return generate_code


def build_generate_router():
    """Build the router that drives the conditional edge off ``generate_code``.

    Reading only the state the node wrote, it routes any generating-stage failure
    (branch preparation, generation, revision, or patch validation/build) to the
    failure sink and an otherwise-built Test Patch to patch review.
    """

    def route_after_generate(state) -> Literal["review", "failed"]:
        return "failed" if state.get("failure") is not None else "review"

    return route_after_generate


def _is_empty_patch(state) -> bool:
    """Whether the current proposal contains no test changes (nothing to apply).

    An empty proposal is either no proposed files at all or a blank canonical diff;
    both mean there is nothing to review, escalate, or commit.
    """
    if not (state.get("generated_files") or []):
        return True
    return not (state.get("diff") or "").strip()


def _post_review_route(review: ReviewResult | None, state, policy: ReviewPolicy) -> Literal["revise", "escalate", "already_covered"]:
    """The post-review destination for a non-failed run.

    An empty proposal is never escalated to the owner: it is retried while Generation
    Retries remain and, once exhausted, reported as the existing tests already covering
    the request (``already_covered``). A non-empty patch escalates to the owner's decision
    when it is accepted or Generation Retries are exhausted, and is otherwise revised.
    """
    retry_available = can_retry_generation(state, limit=policy.max_generation_retries)
    if _is_empty_patch(state):
        return "revise" if retry_available else "already_covered"
    if review is not None and not review.accepted and retry_available:
        return "revise"
    return "escalate"


def build_review_patch_node(code_reviewer, recorder, *, policy: ReviewPolicy):
    """Build the node that statically reviews a generated Test Patch before approval.

    Review is document-grounded static assessment only: the reviewer never executes
    the generated tests, installs dependencies, or implies runtime correctness. The
    reviewer returns a quality ``score`` (0–10); the backend — not the model — owns
    the pass decision, accepting the patch when ``score >= threshold`` (the resolved
    ``policy.pass_threshold``, fixed once at composition). The backend independently re-verifies
    the Test File boundary, so a patch that escapes Test-File scope is rejected even
    when its score passes. The decision is persisted (accepted → awaiting approval,
    rejected → changes requested) and surfaced as a ``ReviewResult`` carrying the
    score, the threshold it was judged against, the findings, and the assessed diff.

    The node returns plain state — never a ``Command`` — leaving post-review routing
    to an explicit conditional edge (see ``build_review_router``). It does emit the
    terminal ``ReviewResult`` whenever the run escalates to the owner (an accepted
    patch, or a below-threshold one with the Generation Retries — bounded by the
    resolved ``ReviewPolicy`` — exhausted), so the escalated patch surfaces its score
    on the Agent Stream; a patch bound for one more Generation Retry stays quiet until
    its re-review.
    """

    pass_threshold = policy.pass_threshold

    def review_patch(state) -> dict:
        coding_run_id = state.get("coding_run_id")
        recorder.begin_reviewing(coding_run_id)
        # A second pass over this node is the review of a Generation Retry; surface it
        # as a distinct stage marker so the Agent Stream tells the two reviews apart.
        emit(Stage(stage="re_reviewing" if is_generation_retry(state) else "reviewing"))
        diff = state.get("diff") or ""
        generated_files = state.get("generated_files") or []

        if _is_empty_patch(state):
            # An empty proposal scores zero deterministically: the backend never asks the
            # reviewer to grade nothing and never lets an empty patch pass the threshold.
            # The post-review router retries it, then reports the tests as already covering.
            score = EMPTY_PATCH_SCORE
            findings = [EMPTY_PATCH_FINDING]
            accepted = False
        else:
            # The reviewer is an LLM/tool loop: a failure in its model call, structured
            # response parsing, or web_search loop is a reviewing-stage Run Failure, not
            # an escaping exception that would leave the run stuck in ``reviewing``.
            try:
                review = code_reviewer.review(
                    task=state["question"],
                    source_documents=state.get("source_documents") or [],
                    test_documents=state.get("test_documents") or [],
                    generated_files=generated_files,
                    diff=diff,
                )
            except Exception:
                logger.exception("Patch review failed")
                return fail_state(RunFailure(failed_stage=CodingRunStage.reviewing, reason=REVIEW_FAILED), trace="review_patch")
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
        # owner; a patch bound for revision or reported as already-covered stays quiet.
        if _post_review_route(review_result, state, policy) == "escalate":
            emit(review_result)
        return {"review_result": review_result, "trace": ["review_patch"]}

    return review_patch


def build_review_router(policy: ReviewPolicy):
    """Build the post-review router that drives the conditional edge off ``review_patch``.

    Reading only the verdict ``review_patch`` wrote to state, it routes the four
    non-trivial outcomes: a reviewing-stage Run Failure routes to the failure sink; a
    below-threshold (or empty) patch with Generation Retries remaining routes back to
    ``generate_code`` for one more Generation Retry; an accepted patch, or a non-empty
    below-threshold one with no Generation Retries remaining routes to the owner's human
    decision; and an empty proposal with no retries remaining routes to the no-changes
    terminal rather than escalating nothing to the owner. Exhaustion escalates or
    reports — it never fails. The router has no side effects; ``review_patch`` already
    emitted the terminal ``ReviewResult`` on the escalation path.
    """

    def route_after_review(state) -> Literal["revise", "escalate", "already_covered", "failed"]:
        if state.get("failure") is not None:
            return "failed"
        return _post_review_route(state.get("review_result"), state, policy)

    return route_after_review


def build_report_no_changes_node(recorder):
    """Build the terminal node for a run that proposed no test changes across all attempts.

    The post-review router routes here when the proposal is still empty after the
    Generation Retries are spent. Rather than escalate an empty patch to the owner, the run
    is recorded as succeeded and a ready-to-show ``RunNoChanges`` is emitted, reporting
    that the existing tests already cover the requested cases.
    """

    def report_no_changes(state) -> dict:
        coding_run_id = state.get("coding_run_id")
        recorder.record_no_changes(coding_run_id)
        outcome = RunNoChanges(coding_run_id=coding_run_id, message=NO_CHANGES_MESSAGE)
        emit(outcome)
        return {"no_changes_result": outcome, "trace": ["report_no_changes"]}

    return report_no_changes


def build_await_decision_node():
    """Build the human-in-the-loop node that suspends a run for the owner's decision.

    The post-review router routes here both for an accepted Patch Review and for a
    below-threshold patch whose Generation Retries is exhausted, so the graph pauses via
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

    The node unpacks state (including the Patch Review the PR body is rendered from),
    builds the publisher and workspace, delegates the commit → push → open-pull-request
    → record-approved → restore-checkout orchestration to the deep ``DecisionFinalizer``,
    and returns plain state — never a ``Command``. A ``git_commit`` / ``git_push`` /
    ``github_pull_request`` Run Failure is folded onto state via ``fail_state`` so the
    post-approval router routes it to the single ``fail_run`` sink, which owns its terminal
    emission; a successful ``RunApproved`` (carrying the opened Pull Request's URL) is
    emitted here and routed to the run's end. The finalizer holds no wire knowledge.
    """

    finalizer = DecisionFinalizer(recorder=recorder)

    def approve_patch(state) -> dict:
        review: ReviewResult | None = state.get("review_result")
        outcome = finalizer.approve(
            publisher=publisher_factory(state["repository_id"]),
            workspace=workspace_factory(state.get("checkout_root")),
            coding_run_id=state.get("coding_run_id"),
            generation_branch=state.get("generation_branch"),
            diff=state.get("diff") or "",
            indexed_commit_sha=state.get("indexed_commit_sha"),
            score=review.score if review is not None else 0,
            threshold=review.threshold if review is not None else 0,
            findings=list(review.findings) if review is not None else [],
        )
        if isinstance(outcome, RunFailure):
            return fail_state(outcome, trace="approve_patch")
        emit(outcome)
        return {"approval_result": outcome, "trace": ["approve_patch"]}

    return approve_patch


def build_approval_router():
    """Build the post-approval router that drives the conditional edge off ``approve_patch``.

    Reading only the state the node wrote, a commit/push Run Failure routes to the
    failure sink while a finalized approval routes to the run's end.
    """

    def route_after_approval(state) -> Literal["approved", "failed"]:
        return "failed" if state.get("failure") is not None else "approved"

    return route_after_approval
