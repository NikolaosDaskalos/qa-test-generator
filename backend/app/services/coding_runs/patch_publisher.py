"""The port the graph uses to publish an approved Test Patch.

Approval is the one code-generation step that needs the network and the
Repository Credential, so the graph stays free of both: the ``approve_patch``
node calls this thin port to commit the reviewed patch on its unique non-default
branch and push it with the credential. ``GitPatchPublisher`` is the production
adapter over ``GitCommands``; tests substitute a fake.
"""

import uuid
from collections.abc import Callable
from typing import Protocol

from app.core import decrypt_repository_token
from app.git import GitCommands, parse_repository_url
from app.models import Repository


class PatchPublisher(Protocol):
    """Commits and pushes one Coding Run's approved Test Patch."""

    def commit(self, message: str) -> None:
        """Commit exactly the reviewed Test Patch on its current (non-default) branch."""

    def push(self) -> None:
        """Push the current branch to the remote with the Repository Credential."""


class GitPatchPublisher:
    """Production ``PatchPublisher`` over ``GitCommands`` for one Repository.

    Built per Repository, it binds a ``GitCommands`` to that Repository's canonical
    identity and owning user and decrypts the stored Repository Credential once. The
    commit runs token-free; the push sends the credential through ``GitCommands``,
    which keeps it out of command-line arguments. Default-branch protection lives in
    ``push_current_branch`` and is not re-implemented here.
    """

    def __init__(self, repository: Repository, *, git_commands_factory: Callable[..., GitCommands] = GitCommands) -> None:
        self._git = git_commands_factory(parse_repository_url(repository.repository_url), repository.user_id)
        self._token = decrypt_repository_token(repository.encrypted_token)

    def commit(self, message: str) -> None:
        self._git.commit(message)

    def push(self) -> None:
        self._git.push_current_branch(self._token)


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
