"""The generation workspace: clean branch prep, validated writes, canonical diff.

The generator proposes complete file contents; the backend — never the model —
prepares an isolated branch, writes only validated Test Files, and derives the
displayed Test Patch from Git. ``LocalGitWorkspace`` operates purely on a local
checkout path with local Git plumbing (no network, no token): it restores the
checkout to the Repository's indexed commit on a uniquely named, non-default
temporary branch, writes files at validated checkout-relative paths, and returns
the canonical unified diff.
"""

import uuid
from pathlib import Path
from typing import Protocol

from app.integrations.git import run_git
from app.schemas import GeneratedFile

# Temporary branches are namespaced and uniquely suffixed, so they are always
# distinct from the Repository's default branch.
GENERATION_BRANCH_PREFIX = "qa-tests"


class GenerationWorkspace(Protocol):
    """Prepares a branch, writes validated Test Files, and derives the Test Patch."""

    def prepare_branch(self, indexed_commit_sha: str) -> str:
        """Restore the checkout to ``indexed_commit_sha`` on a fresh branch; return its name."""

    def reset_patch_state(self) -> None:
        """Clear generated/staged files so a revised proposal replaces the prior one."""

    def discard_generation(self, indexed_commit_sha: str, branch: str) -> None:
        """Restore the checkout to the indexed commit and remove the temporary branch."""

    def write_test_files(self, files: list[GeneratedFile]) -> None:
        """Write each validated Test File's complete contents into the checkout."""

    def diff(self) -> str:
        """Return the canonical unified diff of the checkout against its commit."""


class LocalGitWorkspace:
    """A ``GenerationWorkspace`` over one local checkout, driven by local Git."""

    def __init__(self, checkout_root: Path | str) -> None:
        self.checkout_root = Path(checkout_root)

    def prepare_branch(self, indexed_commit_sha: str) -> str:
        branch = f"{GENERATION_BRANCH_PREFIX}/{uuid.uuid4().hex}"
        run_git("git", "checkout", "-f", "-B", branch, indexed_commit_sha, cwd=self.checkout_root)
        run_git("git", "clean", "-fd", cwd=self.checkout_root)
        return branch

    def reset_patch_state(self) -> None:
        run_git("git", "reset", "--hard", "HEAD", cwd=self.checkout_root)
        run_git("git", "clean", "-fd", cwd=self.checkout_root)

    def discard_generation(self, indexed_commit_sha: str, branch: str) -> None:
        # Force-detach onto the indexed commit so the temporary branch can be removed,
        # drop any working-tree changes, clean untracked files, then delete the branch.
        # All local plumbing: no network, no token, no commit, no push.
        run_git("git", "checkout", "-f", indexed_commit_sha, cwd=self.checkout_root)
        run_git("git", "clean", "-fd", cwd=self.checkout_root)
        run_git("git", "branch", "-D", branch, cwd=self.checkout_root)

    def write_test_files(self, files: list[GeneratedFile]) -> None:
        for file in files:
            destination = self.checkout_root / file.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(file.content)

    def diff(self) -> str:
        run_git("git", "add", "-A", cwd=self.checkout_root)
        return run_git("git", "diff", "--cached", cwd=self.checkout_root).stdout
