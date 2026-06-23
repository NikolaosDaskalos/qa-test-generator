"""The port the graph uses to publish an approved Test Patch.

Approval is the one code-generation step that needs the network and the
Repository Credential, so the graph stays free of both: the ``approve_patch``
node calls this thin port to commit the reviewed patch on its unique non-default
branch and push it with the credential. ``GitPatchPublisher`` is the production
adapter over ``GitCommands``; tests substitute a fake.
"""

import logging
import uuid
from collections.abc import Callable
from typing import Protocol

from github import Auth, Github, GithubException

from app.core import decrypt_repository_token, settings
from app.core.errors.github_errors import GitHubError
from app.db.models import Repository
from app.integrations.git import GitCommands, parse_repository_url

logger = logging.getLogger(__name__)

# User-safe reason for a PR-creation failure; never raw exception text or the credential.
PULL_REQUEST_FAILED = "Could not open a Pull Request for the pushed Test Patch branch."


class PatchPublisher(Protocol):
    """Commits and pushes one Coding Run's approved Test Patch, then opens its Pull Request."""

    def commit(self, message: str) -> None:
        """Commit exactly the reviewed Test Patch on its current (non-default) branch."""

    def push(self) -> None:
        """Push the current branch to the remote with the Repository Credential."""

    def open_pull_request(self, *, title: str, body: str, head: str) -> str:
        """Open a PR from ``head`` into the Repository's default branch; return its URL."""


class GitPatchPublisher:
    """Production ``PatchPublisher`` over ``GitCommands`` for one Repository.

    Built per Repository, it binds a ``GitCommands`` to that Repository's canonical
    identity and owning user and decrypts the stored Repository Credential once. The
    commit runs token-free; the push sends the credential through ``GitCommands``,
    which keeps it out of command-line arguments. Default-branch protection lives in
    ``push_current_branch`` and is not re-implemented here.
    """

    def __init__(
        self,
        repository: Repository,
        *,
        git_commands_factory: Callable[..., GitCommands] = GitCommands,
        github_factory: Callable[..., Github] = Github,
        github_api_base_url: str | None = None,
    ) -> None:
        parsed = parse_repository_url(repository.repository_url)
        self._git = git_commands_factory(parsed, repository.user_id)
        self._token = decrypt_repository_token(repository.encrypted_token)
        self._github_factory = github_factory
        self._github_api_base_url = github_api_base_url or settings.GITHUB_API_BASE_URL
        self._full_name = f"{parsed.owner}/{parsed.name}"

    def commit(self, message: str) -> None:
        self._git.commit(message)

    def push(self) -> None:
        self._git.push_current_branch(self._token)

    def open_pull_request(self, *, title: str, body: str, head: str) -> str:
        """Open a PR from ``head`` into the repo's default branch via PyGithub; map failures to ``GitHubError``."""
        try:
            github = self._github_factory(auth=Auth.Token(self._token), base_url=self._github_api_base_url)
            repository = github.get_repo(self._full_name)
            pull_request = repository.create_pull(title=title, body=body, head=head, base=repository.default_branch)
            return pull_request.html_url
        except GithubException as exc:
            detail = str(exc).replace(self._token, "[REDACTED]") if self._token else str(exc)
            logger.error("Opening Pull Request failed full_name=%s status=%s", self._full_name, getattr(exc, "status", None))
            raise GitHubError(detail[:1000]) from exc


def build_patch_publisher_factory(repository_store, *, git_commands_factory: Callable[..., GitCommands] = GitCommands):
    """Build the factory the graph calls with a ``repository_id`` to get a publisher.

    The factory resolves the Repository through the store and binds a
    ``GitPatchPublisher`` to it, keeping the graph free of persistence and credentials.
    """

    def publisher_factory(repository_id: uuid.UUID) -> GitPatchPublisher:
        repository = repository_store.get_by_id(repository_id)
        return GitPatchPublisher(repository, git_commands_factory=git_commands_factory)

    return publisher_factory


class NullPatchPublisher:
    """A no-op publisher for graph paths compiled without a real credential seam."""

    def commit(self, message: str) -> None:
        return None

    def push(self) -> None:
        return None

    def open_pull_request(self, *, title: str, body: str, head: str) -> str:
        return ""
