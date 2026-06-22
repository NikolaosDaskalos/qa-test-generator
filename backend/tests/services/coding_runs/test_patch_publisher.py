"""Tests for the production ``GitPatchPublisher`` and its factory.

These exercise the credential seam the ``approve_patch`` node depends on: a
publisher commits the reviewed patch and pushes its branch with the decrypted
Repository Credential through ``GitCommands``, never placing the token on a
command line itself (``GitCommands`` owns that guarantee and is tested separately).
"""

import uuid

from app.core import encrypt_repository_token
from app.db.models import Repository
from app.services.coding_runs.patch_publisher import GitPatchPublisher, build_patch_publisher_factory


class FakeGitCommands:
    """Record how the publisher constructs and drives ``GitCommands``."""

    def __init__(self, parsed_repository_url, user_id) -> None:
        self.parsed_repository_url = parsed_repository_url
        self.user_id = user_id
        self.committed = None
        self.push_token = None

    def commit(self, message):
        self.committed = message

    def push_current_branch(self, token):
        self.push_token = token


class FakeRepositoryStore:
    """Return a single repository by id."""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def get_by_id(self, repository_id):
        return self._repository if repository_id == self._repository.id else None


def _repository() -> Repository:
    return Repository(
        user_id=uuid.uuid4(),
        name="fastapi-heroes-app",
        repository_url="https://github.com/NikolaosDaskalos/fastapi-heroes-app.git",
        owner="NikolaosDaskalos",
        encrypted_token=encrypt_repository_token("super-secret-token"),
    )


def test_publisher_commits_and_pushes_with_the_decrypted_credential() -> None:
    """The publisher commits the reviewed patch and pushes the branch with the decrypted token."""
    repository = _repository()
    built: list[FakeGitCommands] = []

    def factory(parsed_repository_url, user_id):
        git = FakeGitCommands(parsed_repository_url, user_id)
        built.append(git)
        return git

    publisher = GitPatchPublisher(repository, git_commands_factory=factory)
    publisher.commit("Add generated tests")
    publisher.push()

    git = built[0]
    # GitCommands is built under the repository's owning user and canonical identity.
    assert git.user_id == repository.user_id
    assert git.parsed_repository_url.canonical_url == repository.repository_url
    # The reviewed patch is committed and the branch pushed with the decrypted credential.
    assert git.committed == "Add generated tests"
    assert git.push_token == "super-secret-token"


def test_factory_builds_a_publisher_for_the_named_repository() -> None:
    """The factory resolves the repository by id and binds a publisher to it."""
    repository = _repository()
    store = FakeRepositoryStore(repository)
    built: list[FakeGitCommands] = []

    def factory(parsed_repository_url, user_id):
        git = FakeGitCommands(parsed_repository_url, user_id)
        built.append(git)
        return git

    publisher_factory = build_patch_publisher_factory(store, git_commands_factory=factory)
    publisher = publisher_factory(repository.id)
    publisher.push()

    assert built[0].user_id == repository.user_id
    assert built[0].push_token == "super-secret-token"
