"""Test repository persistence operations without infrastructure."""

from datetime import UTC, datetime

from app.core.security import encrypt_repository_token
from app.models.git_repositories import GitRepository, GitRepositoryStatus
from app.repositories.git_repository_repository import GitRepositoryRepository


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


def _repository() -> GitRepository:
    return GitRepository(
        user_id="d72745e5-958f-436c-8fc2-d8c2596b33ee",
        name="openai-python",
        repository_url="https://github.com/openai/openai-python.git",
        owner="openai",
        encrypted_token=encrypt_repository_token("old-token"),
        status=GitRepositoryStatus.ready,
    )


def test_update_credentials_persists_only_credential_fields() -> None:
    """Persist encrypted token fields through the repository adapter."""
    session = FakeSession()
    adapter = GitRepositoryRepository(session)
    repository = _repository()
    original_status = repository.status
    expiration = datetime.now(UTC)

    adapter.update_token(
        repository,
        encrypted_token="encrypted-replacement",
        token_expiration_date=expiration,
    )

    assert repository.encrypted_token == "encrypted-replacement"
    assert repository.token_expiration_date == expiration
    assert repository.status == original_status
    assert session.added == [repository]
    assert session.commits == 1
    assert session.refreshes == [repository]


def test_delete_and_rollback_delegate_to_session() -> None:
    """Keep transaction primitives inside the repository adapter."""
    session = FakeSession()
    adapter = GitRepositoryRepository(session)
    repository = _repository()

    adapter.delete(repository)
    adapter.rollback()

    assert session.deleted == [repository]
    assert session.commits == 1
    assert session.rollbacks == 1
