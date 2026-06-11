"""Run bounded Git CLI operations for one validated repository checkout.

This module owns local checkout isolation, non-interactive authentication, Git
process timeouts, and error sanitization. Raw user URLs must be validated by
``parse_repository_url`` before constructing ``GitCommands``.
"""

import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.errors.git_errors import GitError
from app.git.repository_url import ParsedRepositoryUrl, parse_repository_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitResult:
    """Captured standard output and error from a successful Git command."""

    stdout: str
    stderr: str


class GitCommands:
    """Execute Git operations within a user-isolated local checkout.

    The constructor accepts a validated repository value object rather than raw
    input. Network credentials are supplied only to clone, fetch, and push via
    ``GIT_ASKPASS`` and are never included in command-line arguments.
    """

    def __init__(self, parsed_repository_url: ParsedRepositoryUrl, user_id: uuid.UUID) -> None:
        """Build the checkout path for a Git repository owned by an application user."""
        self.parsed_repository_url = parsed_repository_url
        self.repo_path = (
            settings.REPO_PATH / str(user_id) / self.parsed_repository_url.host / self.parsed_repository_url.owner / self.parsed_repository_url.name
        )

    def clone(self, token: str) -> GitResult | None:
        """Clone the repository or safely reuse an equivalent checkout.

        Existing checkouts are reused only when their ``origin`` URL resolves
        to the same canonical repository identity. Partial clone directories
        are removed after failures.

        Args:
            token: Provider access token used for HTTPS authentication.

        Returns:
            The clone result, or ``None`` when a valid checkout already exists.

        Raises:
            GitError: If the path is unsafe, authentication fails, or Git fails.
            ValueError: If an existing checkout has an unsupported origin URL.

        """
        if self._is_git_repository():
            logger.info("Existing Git checkout found path=%s", self.repo_path)
            remote_url = self._run("git", "remote", "get-url", "origin", cwd=self.repo_path).stdout
            if parse_repository_url(remote_url).canonical_url != self.parsed_repository_url.canonical_url:
                logger.error("Existing Git checkout has an unexpected origin path=%s", self.repo_path)
                raise GitError("A different repository already exists at the clone path")
            logger.info("Reusing existing Git checkout path=%s", self.repo_path)
            return None

        if self.repo_path.exists() and any(self.repo_path.iterdir()):
            logger.error("Clone path is non-empty and is not a Git repository path=%s", self.repo_path)
            raise GitError("Clone path exists and is not a Git repository")

        self.repo_path.parent.mkdir(parents=True, exist_ok=True)
        if self.repo_path.exists():
            self.repo_path.rmdir()

        try:
            logger.info(
                "Cloning Git repository host=%s owner=%s repository=%s",
                self.parsed_repository_url.host,
                self.parsed_repository_url.owner,
                self.parsed_repository_url.name,
            )
            return self._run("git", "clone", self.parsed_repository_url.canonical_url, str(self.repo_path), cwd=self.repo_path.parent, token=token)
        except GitError:
            if self.repo_path.exists() and not self._is_git_repository():
                logger.warning("Removing partial Git checkout path=%s", self.repo_path)
                shutil.rmtree(self.repo_path)
            raise

    def get_default_branch(self) -> str:
        """Return the branch referenced by the remote ``origin/HEAD`` symbolic ref.

        Raises:
            GitError: If the remote default branch cannot be determined.

        """
        try:
            result = self._run("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=self.repo_path)
            branch = result.stdout.removeprefix("origin/")
            logger.info("Resolved repository default branch=%s path=%s", branch, self.repo_path)
            return branch
        except GitError as exc:
            logger.error("Could not resolve repository default branch path=%s", self.repo_path)
            raise GitError("Default branch not found") from exc

    def fetch(self, token: str) -> GitResult:
        """Fetch updates from ``origin`` using non-interactive authentication."""
        logger.info("Fetching Git repository path=%s", self.repo_path)
        return self._run("git", "fetch", "origin", cwd=self.repo_path, token=token)

    def delete_checkout(self) -> None:
        """Delete this repository's checkout without trusting persisted paths.

        Raises:
            GitError: If the computed checkout is a symlink, is outside the
                configured repository root, or is not a directory.

        """
        repository_root = settings.REPO_PATH.resolve()
        if self.repo_path.is_symlink():
            logger.error("Refusing to delete symlinked repository checkout path=%s", self.repo_path)
            raise GitError("Repository checkout path cannot be a symlink")

        checkout_path = self.repo_path.resolve()
        if checkout_path == repository_root or not checkout_path.is_relative_to(repository_root):
            logger.error("Refusing to delete checkout outside repository root path=%s", checkout_path)
            raise GitError("Repository checkout path is outside the repository root")
        if not checkout_path.exists():
            logger.warning("Repository checkout does not exist path=%s", checkout_path)
            return
        if not checkout_path.is_dir():
            logger.error("Repository checkout path is not a directory path=%s", checkout_path)
            raise GitError("Repository checkout path is not a directory")

        logger.info("Deleting repository checkout path=%s", checkout_path)
        shutil.rmtree(checkout_path)
        logger.info("Repository checkout deleted path=%s", checkout_path)

    def commit(self, commit_msg: str) -> GitResult:
        """Stage all checkout changes and create a local commit.

        Raises:
            GitError: If the message is empty or either Git command fails.

        """
        if not commit_msg:
            logger.warning("Git commit rejected because the commit message is empty path=%s", self.repo_path)
            raise GitError("Commit message cannot be empty")
        logger.info("Creating Git commit path=%s", self.repo_path)
        self._run("git", "add", ".", cwd=self.repo_path)
        return self._run("git", "commit", "-m", commit_msg, cwd=self.repo_path)

    def push_current_branch(self, token: str) -> GitResult:
        """Push the current branch while protecting the remote default branch.

        The operation fails closed when either the current branch or the remote
        default branch cannot be determined.

        Raises:
            GitError: If branch detection fails, the current branch is the
                default branch, or the push fails.

        """
        branch = self._run("git", "branch", "--show-current", cwd=self.repo_path).stdout

        if not branch:
            logger.error("Cannot push because the current branch could not be determined path=%s", self.repo_path)
            raise GitError("Current branch not found")
        if branch == self.get_default_branch():
            logger.warning("Blocked push to default branch=%s path=%s", branch, self.repo_path)
            raise GitError("Push to the default branch is not supported")
        logger.info("Pushing Git branch=%s path=%s", branch, self.repo_path)
        return self._run("git", "push", "origin", "HEAD", cwd=self.repo_path, token=token)

    def checkout(self, branch_name: str) -> GitResult:
        """Reset a local branch to its matching ``origin`` branch and check it out.

        Raises:
            GitError: If the branch name is empty or Git cannot check it out.

        """
        branch_name = branch_name.strip()
        if not branch_name:
            logger.warning("Git checkout rejected because the branch name is empty path=%s", self.repo_path)
            raise GitError("Branch name cannot be empty")
        logger.info("Checking out Git branch=%s path=%s", branch_name, self.repo_path)
        return self._run("git", "checkout", "-B", branch_name, f"origin/{branch_name}", cwd=self.repo_path)

    def _is_git_repository(self) -> bool:
        return (self.repo_path / ".git").is_dir()

    def _run(self, *args: str, cwd: Path, token: str | None = None) -> GitResult:
        """Run Git without a shell and translate process failures to ``GitError``.

        Tokens are passed through a child-process-only environment and redacted
        from captured failures before the error reaches application logs.
        """
        command = " ".join(args[:2])
        logger.info("Running Git command=%s cwd=%s authenticated=%s", command, cwd, token is not None)
        environment = os.environ.copy()
        if token is not None:
            environment.update(
                {
                    "GIT_ASKPASS": str(Path(__file__).with_name("git_askpass.py").resolve()),
                    "GIT_ASKPASS_REQUIRE": "force",
                    "GIT_TERMINAL_PROMPT": "0",
                    "QA_GIT_USERNAME": self._credential_username(),
                    "QA_GIT_TOKEN": token,
                }
            )

        try:
            result = subprocess.run([*args], cwd=cwd.resolve(), timeout=120, text=True, check=True, shell=False, capture_output=True, env=environment)
        except subprocess.TimeoutExpired as exc:
            logger.error("Git command timed out command=%s cwd=%s", command, cwd)
            raise GitError("Git command timed out") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "Git command failed").strip()
            if token:
                detail = detail.replace(token, "[REDACTED]")
            logger.error("Git command failed command=%s cwd=%s return_code=%s", command, cwd, exc.returncode)
            raise GitError(detail[:1000]) from exc

        logger.info("Git command completed command=%s cwd=%s", command, cwd)
        return GitResult(stdout=result.stdout.strip(), stderr=result.stderr.strip())

    def _credential_username(self) -> str:
        usernames = {"github.com": "x-access-token", "gitlab.com": "oauth2", "bitbucket.org": "x-token-auth"}
        return usernames[self.parsed_repository_url.host]
