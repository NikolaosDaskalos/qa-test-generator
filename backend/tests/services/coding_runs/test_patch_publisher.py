"""Tests for the production ``GitPatchPublisher`` and its factory.

These exercise the credential seam the ``approve_patch`` node depends on: a
publisher commits the reviewed patch and pushes its branch with the decrypted
Repository Credential through ``GitCommands``, never placing the token on a
command line itself (``GitCommands`` owns that guarantee and is tested separately).
"""

import uuid

import pytest

from app.core import encrypt_repository_token
from app.core.errors.github_errors import GitHubError
from app.db.models import Repository
from app.services.coding_runs.patch_publisher import GitPatchPublisher, build_patch_publisher_factory


class FakePullRequest:
    """A created pull request exposing its web URL like PyGithub's ``PullRequest``."""

    def __init__(self, html_url: str) -> None:
        self.html_url = html_url


class FakeGithubRepository:
    """A PyGithub ``Repository`` stand-in: records ``create_pull`` and reports a default branch."""

    def __init__(self, *, default_branch: str = "main", html_url: str = "https://github.com/o/r/pull/7", error: Exception | None = None) -> None:
        self.default_branch = default_branch
        self._html_url = html_url
        self._error = error
        self.create_pull_kwargs = None

    def create_pull(self, **kwargs):
        self.create_pull_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return FakePullRequest(self._html_url)


class FakeGithub:
    """A PyGithub ``Github`` client stand-in: records its construction and returns a repository."""

    def __init__(self, repository: FakeGithubRepository) -> None:
        self._repository = repository
        self.auth = None
        self.base_url = None
        self.requested_full_name = None

    def get_repo(self, full_name):
        self.requested_full_name = full_name
        return self._repository


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


def _github_factory(github: FakeGithub):
    """Build a PyGithub-client factory recording the credential and base URL it is constructed with."""
    captured: dict = {}

    def factory(*, auth, base_url):
        captured["auth"] = auth
        captured["base_url"] = base_url
        return github

    return factory, captured


def test_open_pull_request_targets_the_default_branch_and_returns_the_pr_url() -> None:
    """The publisher opens a PR from the generation branch into the repo's default branch and returns its URL."""
    repository = _repository()
    gh_repo = FakeGithubRepository(default_branch="main", html_url="https://github.com/NikolaosDaskalos/fastapi-heroes-app/pull/7")
    github = FakeGithub(gh_repo)
    factory, captured = _github_factory(github)

    publisher = GitPatchPublisher(
        repository, git_commands_factory=FakeGitCommands, github_factory=factory, github_api_base_url="https://api.github.com"
    )
    url = publisher.open_pull_request(title="Add generated tests", body="## Patch Review", head="qa-tests/fake")

    # The PR is opened from the generation branch into the repository's default branch as the base.
    assert gh_repo.create_pull_kwargs["base"] == "main"
    assert gh_repo.create_pull_kwargs["head"] == "qa-tests/fake"
    assert gh_repo.create_pull_kwargs["title"] == "Add generated tests"
    assert gh_repo.create_pull_kwargs["body"] == "## Patch Review"
    # The PyGithub client is built with the decrypted credential and the configured API base URL.
    assert captured["auth"].token == "super-secret-token"
    assert captured["base_url"] == "https://api.github.com"
    # The owning repository is addressed by its owner/name, and the created PR's URL is returned.
    assert github.requested_full_name == "NikolaosDaskalos/fastapi-heroes-app"
    assert url == "https://github.com/NikolaosDaskalos/fastapi-heroes-app/pull/7"


def test_open_pull_request_redacts_the_credential_from_a_github_failure(caplog) -> None:
    """A PyGithub failure becomes a sanitized GitHubError with the credential redacted from the message and logs."""
    from github import GithubException

    repository = _repository()
    error = GithubException(422, data={"message": "Validation failed for super-secret-token"}, headers=None)
    gh_repo = FakeGithubRepository(error=error)
    factory, _ = _github_factory(FakeGithub(gh_repo))

    publisher = GitPatchPublisher(repository, git_commands_factory=FakeGitCommands, github_factory=factory)

    with pytest.raises(GitHubError) as raised:
        publisher.open_pull_request(title="Add generated tests", body="## Patch Review", head="qa-tests/fake")

    assert "super-secret-token" not in str(raised.value)
    assert "super-secret-token" not in caplog.text


def test_open_pull_request_permission_denied_is_a_sanitized_github_error() -> None:
    """A credential lacking PR write permission (403) surfaces as a sanitized GitHubError, not an escaping exception."""
    from github import GithubException

    repository = _repository()
    error = GithubException(403, data={"message": "Resource not accessible by personal access token"}, headers=None)
    gh_repo = FakeGithubRepository(error=error)
    factory, _ = _github_factory(FakeGithub(gh_repo))

    publisher = GitPatchPublisher(repository, git_commands_factory=FakeGitCommands, github_factory=factory)

    with pytest.raises(GitHubError):
        publisher.open_pull_request(title="Add generated tests", body="## Patch Review", head="qa-tests/fake")


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
