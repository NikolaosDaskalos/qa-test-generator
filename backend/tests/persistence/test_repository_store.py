"""Test Git repository persistence operations without infrastructure."""

from datetime import UTC, datetime

from app.core import encrypt_repository_token
from app.enums import RepositoryStatus
from app.errors.git_errors import GitError
from app.models import Repository
from app.persistence import RepositoryStore


class FakeSession:
    """Record session mutations and transaction boundaries."""

    def __init__(self) -> None:
        self.added = []
        self.deleted = []
        self.commits = 0
        self.refreshes = []
        self.rollbacks = 0

    def add(self, value) -> None:
        self.added.append(value)

    def delete(self, value) -> None:
        self.deleted.append(value)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value) -> None:
        self.refreshes.append(value)

    def rollback(self) -> None:
        self.rollbacks += 1


def _repository() -> Repository:
    return Repository(
        user_id="d72745e5-958f-436c-8fc2-d8c2596b33ee",
        name="openai-python",
        repository_url="https://github.com/openai/openai-python.git",
        owner="openai",
        encrypted_token=encrypt_repository_token("old-token"),
        status=RepositoryStatus.ready,
    )


def test_update_credentials_persists_only_credential_fields() -> None:
    """Persist encrypted token fields through the Git repository store."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()
    original_status = repository.status
    expiration = datetime.now(UTC)

    repository_store.update_token(repository, encrypted_token="encrypted-replacement", token_expiration_date=expiration)

    assert repository.encrypted_token == "encrypted-replacement"
    assert repository.token_expiration_date == expiration
    assert repository.status == original_status
    assert session.added == [repository]
    assert session.commits == 1
    assert session.refreshes == [repository]


def test_mark_ready_persists_indexed_commit_and_status_together() -> None:
    """Publish Repository Evidence and its exact commit in one transaction."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()
    repository.status = RepositoryStatus.indexing

    repository_store.mark_ready(repository, indexed_commit_sha="a" * 40)

    assert repository.indexed_commit_sha == "a" * 40
    assert repository.status == RepositoryStatus.ready
    assert session.added == [repository]
    assert session.commits == 1
    assert session.refreshes == [repository]


def test_begin_cloning_moves_status_and_clears_prior_failure() -> None:
    """Enter the cloning state and drop any stale failure reason."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()
    repository.status = RepositoryStatus.pending
    repository.failed_reason = "previous failure"

    repository_store.begin_cloning(repository)

    assert repository.status == RepositoryStatus.cloning
    assert repository.failed_reason is None
    assert session.added == [repository]
    assert session.commits == 1


def test_record_checkout_persists_local_path_and_default_branch_together() -> None:
    """Capture the checkout location and branch in one transaction."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()
    repository.status = RepositoryStatus.cloning

    repository_store.record_checkout(repository, local_path="/tmp/checkout", default_branch="main")

    assert repository.local_path == "/tmp/checkout"
    assert repository.default_branch == "main"
    assert repository.status == RepositoryStatus.cloning
    assert session.added == [repository]
    assert session.commits == 1


def test_begin_indexing_moves_status_to_indexing() -> None:
    """Enter the indexing state after a successful checkout."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()
    repository.status = RepositoryStatus.cloning

    repository_store.begin_indexing(repository)

    assert repository.status == RepositoryStatus.indexing
    assert session.added == [repository]
    assert session.commits == 1


def test_fail_redacts_credential_and_persists_failed_status() -> None:
    """Stamp a failure whose domain message cannot expose the credential."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()
    repository.status = RepositoryStatus.cloning
    credential = "secret-token"

    reason = repository_store.fail(repository, GitError(f"Authentication failed for {credential}"), credential=credential)

    assert reason == "Authentication failed for [REDACTED]"
    assert repository.status == RepositoryStatus.failed
    assert repository.failed_reason == "Authentication failed for [REDACTED]"
    assert credential not in repository.failed_reason
    assert session.added == [repository]
    assert session.commits == 1


def test_fail_uses_fallback_for_non_domain_errors_and_caps_length() -> None:
    """Hide non-domain internals behind the fallback and bound the reason length."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()

    reason = repository_store.fail(repository, RuntimeError("psycopg leaked internal detail"), credential=None, fallback="Repository vector deletion failed")

    assert reason == "Repository vector deletion failed"

    long_message = "x" * 1100
    capped = repository_store.fail(repository, GitError(long_message), credential=None)

    assert len(capped) == 1000


def test_delete_and_rollback_delegate_to_session() -> None:
    """Keep transaction primitives inside the Git repository store."""
    session = FakeSession()
    repository_store = RepositoryStore(session)
    repository = _repository()

    repository_store.delete(repository)
    repository_store.rollback()

    assert session.deleted == [repository]
    assert session.commits == 1
    assert session.rollbacks == 1
