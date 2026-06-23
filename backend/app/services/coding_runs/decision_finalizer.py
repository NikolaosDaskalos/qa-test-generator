"""Deep finalizer for the owner's approve/reject decision behind thin graph nodes.

The owner's human-in-the-loop decision on an accepted Test Patch is finalized here
from plain inputs: ``approve`` commits the reviewed patch on its unique non-default
branch, pushes it with the Repository Credential, records the run approved, and
restores the checkout — mapping a commit or push failure to a typed ``git_commit`` /
``git_push`` Run Failure. ``discard`` restores the checkout, removes the temporary
branch, and records the run rejected. The shared checkout-restore / branch-cleanup
step lives once here. The finalizer holds no wire knowledge: it returns a typed
``RunApproved`` / ``RunRejected`` / ``RunFailure`` outcome — never an escaping
exception and never a raw state dict — and the thin graph node emits it.
"""

import logging
import uuid

from app.enums import CodingRunStage
from app.schemas import ReviewFinding, RunApproved, RunFailure, RunRejected
from app.services.coding_runs.workspace import GenerationWorkspace

logger = logging.getLogger(__name__)

# The fixed commit message and Pull Request title for an approved Test Patch; the run identity lives on the Coding Run.
APPROVAL_COMMIT_MESSAGE = "Add generated tests"
PULL_REQUEST_TITLE = "Add generated tests"
# User-safe reasons for an approval-stage failure; never raw exception text or the credential.
COMMIT_FAILED = "Could not commit the approved Test Patch."
PUSH_FAILED = "Could not push the approved Test Patch branch."
# The branch is already on the remote; only Pull Request creation failed.
PULL_REQUEST_FAILED = "Pushed the Test Patch branch, but could not open a Pull Request for it."


def _pull_request_message(url: str) -> str:
    """Ready-to-show copy pointing the owner to the opened Pull Request."""
    return f"Your tests were pushed and a Pull Request was opened for review: {url}"


def _pull_request_body(score: int, threshold: int, findings: list[ReviewFinding]) -> str:
    """Render the Patch Review — score, configured pass threshold, and categorized findings — as the PR body."""
    lines = [
        "## Patch Review",
        "",
        f"**Score:** {score}/10 (pass threshold: {threshold})",
        "",
        "_The generated tests were not executed; runtime correctness was not verified._",
        "",
        "### Findings",
    ]
    if findings:
        lines += [f"- **{finding.category}:** {finding.detail}" for finding in findings]
    else:
        lines.append("- None.")
    return "\n".join(lines)


class DecisionFinalizer:
    """Finalize the owner's approve/reject decision on a reviewed Test Patch."""

    def __init__(self, *, recorder) -> None:
        self._recorder = recorder

    def approve(
        self,
        *,
        publisher,
        workspace: GenerationWorkspace,
        coding_run_id: uuid.UUID,
        generation_branch: str,
        diff: str,
        indexed_commit_sha: str,
        score: int,
        threshold: int,
        findings: list[ReviewFinding],
    ) -> RunApproved | RunFailure:
        """Commit, push, open the PR, record approved, and restore the checkout; map failures to a typed Run Failure.

        Push happens before PR creation, so a PR failure (a distinct ``github_pull_request`` stage)
        means the branch is on the remote but no Pull Request was opened — never approving or restoring.
        """
        try:
            publisher.commit(APPROVAL_COMMIT_MESSAGE)
        except Exception:
            logger.error("Approved patch commit failed: %s", COMMIT_FAILED)
            return RunFailure(failed_stage=CodingRunStage.git_commit, reason=COMMIT_FAILED)
        try:
            publisher.push()
        except Exception:
            logger.error("Approved patch push failed: %s", PUSH_FAILED)
            return RunFailure(failed_stage=CodingRunStage.git_push, reason=PUSH_FAILED)
        try:
            pull_request_url = publisher.open_pull_request(
                title=PULL_REQUEST_TITLE, body=_pull_request_body(score, threshold, findings), head=generation_branch or ""
            )
        except Exception:
            logger.error("Approved patch Pull Request creation failed: %s", PULL_REQUEST_FAILED)
            return RunFailure(failed_stage=CodingRunStage.github_pull_request, reason=PULL_REQUEST_FAILED)
        self._recorder.approve(coding_run_id, pull_request_url=pull_request_url)
        self._restore_checkout(workspace, indexed_commit_sha, generation_branch)
        branch = generation_branch or ""
        return RunApproved(
            coding_run_id=coding_run_id, branch=branch, diff=diff or "", pull_request_url=pull_request_url, message=_pull_request_message(pull_request_url)
        )

    def discard(
        self,
        *,
        workspace: GenerationWorkspace,
        coding_run_id: uuid.UUID,
        generation_branch: str,
        diff: str,
        indexed_commit_sha: str,
        findings: list[ReviewFinding],
    ) -> RunRejected:
        """Restore the checkout, remove the temporary branch, record rejected, and return the outcome."""
        self._restore_checkout(workspace, indexed_commit_sha, generation_branch)
        self._recorder.reject(coding_run_id)
        return RunRejected(coding_run_id=coding_run_id, diff=diff or "", findings=list(findings))

    def _restore_checkout(self, workspace: GenerationWorkspace, indexed_commit_sha: str, branch: str) -> None:
        """Restore the shared checkout to the indexed commit and remove the temporary branch (local Git only)."""
        workspace.discard_generation(indexed_commit_sha, branch)
