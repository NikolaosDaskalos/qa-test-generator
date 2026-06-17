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

from app.agent.workspace import GenerationWorkspace
from app.enums.coding_run import CodingRunStage
from app.schemas.agent_stream import RunApproved, RunFailure, RunRejected
from app.schemas.review import ReviewFinding

logger = logging.getLogger(__name__)

# The fixed commit message for an approved Test Patch; the run identity lives on the Coding Run, not the message.
APPROVAL_COMMIT_MESSAGE = "Add generated tests"
# User-safe reasons for an approval-stage Git failure; never raw exception text or the credential.
COMMIT_FAILED = "Could not commit the approved Test Patch."
PUSH_FAILED = "Could not push the approved Test Patch branch."


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
    ) -> RunApproved | RunFailure:
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
        self._recorder.approve(coding_run_id)
        self._restore_checkout(workspace, indexed_commit_sha, generation_branch)
        return RunApproved(coding_run_id=coding_run_id, branch=generation_branch or "", diff=diff or "")

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
        self._restore_checkout(workspace, indexed_commit_sha, generation_branch)
        self._recorder.reject(coding_run_id)
        return RunRejected(coding_run_id=coding_run_id, diff=diff or "", findings=list(findings))

    def _restore_checkout(self, workspace: GenerationWorkspace, indexed_commit_sha: str, branch: str) -> None:
        """Restore the shared checkout to the indexed commit and remove the temporary branch (local Git only)."""
        workspace.discard_generation(indexed_commit_sha, branch)
