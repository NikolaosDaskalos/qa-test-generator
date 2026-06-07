"""Run bounded Git CLI operations for one validated repository checkout.

This module owns local checkout isolation, non-interactive authentication, Git
process timeouts, and error sanitization. Raw user URLs must be validated by
``parse_repository_url`` before constructing ``GitCommands``.
"""

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.errors.git_errors import GitError
from app.git.repository_url import (
    ParsedRepositoryUrl,
    parse_repository_url,
)


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

    def __init__(
        self,
        repository: ParsedRepositoryUrl,
        user_id: uuid.UUID,
    ) -> None:
        """Build the checkout path for a repository owned by an application user."""
        self.repository = repository
        self.repo_path = (
            settings.REPO_PATH
            / str(user_id)
            / self.repository.host
            / self.repository.owner
            / self.repository.name
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
            remote_url = self._run(
                "git",
                "remote",
                "get-url",
                "origin",
                cwd=self.repo_path,
            ).stdout
            if (
                parse_repository_url(remote_url).canonical_url
                != self.repository.canonical_url
            ):
                raise GitError(
                    "A different repository already exists at the clone path"
                )
            return None

        if self.repo_path.exists() and any(self.repo_path.iterdir()):
            raise GitError("Clone path exists and is not a Git repository")

        self.repo_path.parent.mkdir(parents=True, exist_ok=True)
        if self.repo_path.exists():
            self.repo_path.rmdir()

        try:
            return self._run(
                "git",
                "clone",
                self.repository.canonical_url,
                str(self.repo_path),
                cwd=self.repo_path.parent,
                token=token,
            )
        except GitError:
            if self.repo_path.exists() and not self._is_git_repository():
                shutil.rmtree(self.repo_path)
            raise

    def get_default_branch(self) -> str:
        """Return the branch referenced by the remote ``origin/HEAD`` symbolic ref.

        Raises:
            GitError: If the remote default branch cannot be determined.

        """
        try:
            result = self._run(
                "git",
                "symbolic-ref",
                "--short",
                "refs/remotes/origin/HEAD",
                cwd=self.repo_path,
            )
            return result.stdout.removeprefix("origin/")
        except GitError as exc:
            raise GitError("Default branch not found") from exc

    def fetch(self, token: str) -> GitResult:
        """Fetch updates from ``origin`` using non-interactive authentication."""
        return self._run(
            "git",
            "fetch",
            "origin",
            cwd=self.repo_path,
            token=token,
        )

    def commit(self, commit_msg: str) -> GitResult:
        """Stage all checkout changes and create a local commit.

        Raises:
            GitError: If the message is empty or either Git command fails.

        """
        if not commit_msg:
            raise GitError("Commit message cannot be empty")
        self._run("git", "add", ".", cwd=self.repo_path)
        return self._run(
            "git",
            "commit",
            "-m",
            commit_msg,
            cwd=self.repo_path,
        )

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
            raise GitError("Current branch not found")
        if branch == self.get_default_branch():
            raise GitError("Push to the default branch is not supported")
        return self._run(
            "git", "push", "origin", "HEAD", cwd=self.repo_path, token=token
        )

    def checkout(self, branch_name: str) -> GitResult:
        """Reset a local branch to its matching ``origin`` branch and check it out.

        Raises:
            GitError: If the branch name is empty or Git cannot check it out.

        """
        branch_name = branch_name.strip()
        if not branch_name:
            raise GitError("Branch name cannot be empty")
        return self._run(
            "git",
            "checkout",
            "-B",
            branch_name,
            f"origin/{branch_name}",
            cwd=self.repo_path,
        )

    def _is_git_repository(self) -> bool:
        return (self.repo_path / ".git").is_dir()

    def _run(
        self,
        *args: str,
        cwd: Path,
        token: str | None = None,
    ) -> GitResult:
        """Run Git without a shell and translate process failures to ``GitError``.

        Tokens are passed through a child-process-only environment and redacted
        from captured failures before the error reaches application logs.
        """
        environment = os.environ.copy()
        if token is not None:
            environment.update(
                {
                    "GIT_ASKPASS": str(
                        Path(__file__).with_name("git_askpass.py").resolve()
                    ),
                    "GIT_ASKPASS_REQUIRE": "force",
                    "GIT_TERMINAL_PROMPT": "0",
                    "QA_GIT_USERNAME": self._credential_username(),
                    "QA_GIT_TOKEN": token,
                }
            )

        try:
            result = subprocess.run(
                [*args],
                cwd=cwd.resolve(),
                timeout=120,
                text=True,
                check=True,
                shell=False,
                capture_output=True,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError("Git command timed out") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "Git command failed").strip()
            if token:
                detail = detail.replace(token, "[REDACTED]")
            raise GitError(detail[:1000]) from exc

        return GitResult(
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )

    def _credential_username(self) -> str:
        usernames = {
            "github.com": "x-access-token",
            "gitlab.com": "oauth2",
            "bitbucket.org": "x-token-auth",
        }
        return usernames[self.repository.host]
