"""The ``test_generation`` generic retrieve node.

This node executes the planner's Research Intents under the session's Repository
identity. Each intent's untrusted candidate paths are confined to the checkout
(unsafe ones dropped) before any survive into state as validated retrieval hints.
Retrieved Repository Evidence is partitioned by the intent's tag into separate
``source_evidence`` (what's implemented) and ``test_evidence`` (what's already
tested), which are kept apart on the shared state.
"""

import logging
from pathlib import Path

from app.agent.paths import confine_candidate_paths
from app.agent.stream import emit
from app.agent.test_files import RejectedTestFile, discover_test_roots, validate_test_file
from app.core.config import settings
from app.enums.coding_run import CodingRunStatus
from app.schemas.agent_stream import PatchResult, ReviewResult, RunFailure, Stage
from app.schemas.review import ReviewFinding

logger = logging.getLogger(__name__)

# User-safe reasons for a generating-stage failure; never raw exception text.
BRANCH_PREPARATION_FAILED = "Could not prepare a clean branch to generate tests on."
GENERATION_FAILED = "The test generator could not produce a valid proposal."
REVISION_FAILED = "The test generator could not revise its proposal."
PATCH_DERIVATION_FAILED = "Could not write the generated tests or derive the patch."
# User-safe reasons for a reviewing-stage failure; never raw exception text.
REVIEW_FAILED = "The patch reviewer could not complete its assessment."
SECOND_REVIEW_REJECTED = "The reviewer rejected the revised tests after one revision attempt."


def build_gather_evidence_node(retriever):
    """Build the generic retrieve node that partitions evidence source vs. test."""

    def gather_evidence(state) -> dict:
        repository_id = state["repository_id"]
        checkout_root = state.get("checkout_root")
        source_evidence: list = []
        test_evidence: list = []
        hints: list[str] = []

        for intent in state.get("research_intents") or []:
            if checkout_root and intent.candidate_paths:
                hints.extend(confine_candidate_paths(Path(checkout_root), intent.candidate_paths))
            evidence = retriever.retrieve_evidence(
                intent.description,
                repository_id=repository_id,
                k=settings.TOP_K,
                alpha=settings.HYBRID_SEARCH_ALPHA,
                parent_limit=settings.FINAL_PARENT_LIMIT,
            )
            target = source_evidence if intent.target == "source" else test_evidence
            target.extend(evidence)

        return {
            "source_evidence": source_evidence,
            "test_evidence": test_evidence,
            "candidate_hints": _dedupe(hints),
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
        recorder.advance(state["coding_run_id"], CodingRunStatus.generating)
        try:
            workspace = workspace_factory(state.get("checkout_root"))
            branch = workspace.prepare_branch(state.get("indexed_commit_sha"))
        except Exception:
            logger.exception("Generation branch preparation failed")
            return {"failure": RunFailure(failed_stage="generating", reason=BRANCH_PREPARATION_FAILED), "trace": ["prepare_branch"]}
        return {"generation_branch": branch, "trace": ["prepare_branch"]}

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
                task=state["question"],
                source_evidence=state.get("source_evidence") or [],
                test_evidence=state.get("test_evidence") or [],
            )
        except Exception:
            logger.exception("Test generation failed")
            return {"failure": RunFailure(failed_stage="generating", reason=GENERATION_FAILED), "trace": ["generate_tests"]}
        return {
            "generated_files": proposal.generated_files,
            "external_references": proposal.external_references,
            "trace": ["generate_tests"],
        }

    return generate_tests


def build_revise_tests_node(generator):
    """Build the node that performs one bounded Revision Attempt after a rejection.

    The generator is handed the original task, partitioned Repository Evidence, its
    own prior complete-file proposal, the canonical diff that was reviewed, and the
    reviewer's findings, and may replace the proposal once. The revised files flow
    back through the same write/validation/review path as initial generation; a
    generator failure here is a generating-stage Run Failure. ``revision_attempts``
    is stamped so the post-review router admits no second revision.
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
            return {"failure": RunFailure(failed_stage="generating", reason=REVISION_FAILED), "trace": ["revise_tests"]}
        return {
            "generated_files": proposal.generated_files,
            "external_references": proposal.external_references,
            "revision_attempts": 1,
            "trace": ["revise_tests"],
        }

    return revise_tests


def build_build_patch_node(workspace_factory, recorder):
    """Build the node that validates, writes, and derives the canonical Test Patch.

    Each proposed path is validated before any write; an unsafe path, a non-Python
    file, or application code is a generating-stage Run Failure. Validated files are
    written and the displayed diff is obtained from Git, then the Coding Run
    persists the proposals, External References, and canonical diff.
    """

    def build_patch(state) -> dict:
        checkout_root = Path(state["checkout_root"]) if state.get("checkout_root") else None
        # Discover the Repository's existing test roots once, before any proposal is
        # written, so new files are admitted only beneath an established root.
        test_roots = discover_test_roots(checkout_root) if checkout_root else frozenset()
        try:
            validated = [
                file.model_copy(update={"path": validate_test_file(checkout_root, file.path, test_roots)}) for file in state.get("generated_files") or []
            ]
        except RejectedTestFile as rejection:
            return {"failure": RunFailure(failed_stage="generating", reason=rejection.reason), "trace": ["build_patch"]}

        try:
            workspace = workspace_factory(state.get("checkout_root"))
            if state.get("revision_attempts"):
                workspace.reset_patch_state()
            workspace.write_test_files(validated)
            diff = workspace.diff()
        except Exception:
            logger.exception("Patch derivation failed")
            return {"failure": RunFailure(failed_stage="generating", reason=PATCH_DERIVATION_FAILED), "trace": ["build_patch"]}

        coding_run_id = state.get("coding_run_id")
        external_references = state.get("external_references") or []
        recorder.complete(
            coding_run_id,
            branch=state.get("generation_branch"),
            diff=diff,
            generated_files=validated,
            external_references=external_references,
        )
        patch_result = PatchResult(coding_run_id=coding_run_id, diff=diff, generated_files=validated, external_references=external_references)
        return {"patch_result": patch_result, "diff": diff, "generated_files": validated, "trace": ["build_patch"]}

    return build_patch


def build_review_patch_node(reviewer, recorder):
    """Build the node that statically reviews a generated Test Patch before approval.

    Review is evidence-based static assessment only: the reviewer never executes
    the generated tests, installs dependencies, or implies runtime correctness. The
    backend independently re-verifies the Test File boundary, so a patch that
    escapes Test-File scope is rejected even when the reviewer accepts it. The
    decision is persisted (accepted → awaiting approval, rejected → changes
    requested) and surfaced as a ``ReviewResult`` carrying the findings and the
    assessed diff.
    """

    def review_patch(state) -> dict:
        coding_run_id = state.get("coding_run_id")
        recorder.advance(coding_run_id, CodingRunStatus.reviewing)
        # A second pass over this node is the review of a Revision Attempt; surface it
        # as a distinct stage marker so the Agent Stream tells the two reviews apart.
        emit(Stage(stage="re_reviewing" if state.get("revision_attempts") else "reviewing"))
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
            return {"failure": RunFailure(failed_stage="reviewing", reason=REVIEW_FAILED), "trace": ["review_patch"]}
        accepted = bool(review.accepted)
        findings = list(review.findings)

        # The reviewer's acceptance is never the sole gate: the backend independently
        # re-verifies that every proposal stays within the Test File boundary.
        boundary_finding = _verify_test_file_boundary(state.get("checkout_root"), generated_files)
        if boundary_finding is not None:
            accepted = False
            findings = [*findings, boundary_finding]

        recorder.record_review(coding_run_id, accepted=accepted, findings=findings)
        review_result = ReviewResult(coding_run_id=coding_run_id, accepted=accepted, findings=findings, diff=diff)
        return {"review_result": review_result, "trace": ["review_patch"]}

    return review_patch


def _verify_test_file_boundary(checkout_root, generated_files) -> ReviewFinding | None:
    """Independently re-assert the Test File boundary over the proposed files.

    Returns a ``scope`` finding for the first proposal that escapes Test-File
    scope, or ``None`` when every proposal is within bounds.
    """
    if not checkout_root:
        return None
    root = Path(checkout_root)
    test_roots = discover_test_roots(root)
    for file in generated_files:
        try:
            validate_test_file(root, file.path, test_roots)
        except RejectedTestFile as rejection:
            return ReviewFinding(category="scope", detail=rejection.reason)
    return None


def _dedupe(paths: list[str]) -> list[str]:
    """Drop duplicate validated hints while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered
