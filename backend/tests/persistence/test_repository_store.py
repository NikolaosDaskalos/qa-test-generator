"""Test Git repository persistence operations without infrastructure."""

from datetime import UTC, datetime

from app.core.security import encrypt_repository_token
from app.enums.repository import RepositoryStatus
from app.models.repository import Repository
from app.persistence.repository_store import RepositoryStore


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
