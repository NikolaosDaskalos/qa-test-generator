import subprocess
import sys
import uuid
from datetime import timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import configure_mappers
from sqlmodel import Session, SQLModel, select

from app.enums import RepositoryProvider, RepositoryStatus
from app.models import Repository, RepositorySession, SessionHistory, SourceDocument, User
from app.schemas import RepositoryCreate, RepositoryPublic


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    return "JSON"


def test_repository_token_fields_are_on_repository() -> None:
    assert "encrypted_token" in Repository.model_fields
    assert "token_expiration_date" in Repository.model_fields


def test_repository_create_requires_token_and_allows_no_expiration() -> None:
    repository_in = RepositoryCreate(repository_url="git@github.com:openai/openai-python.git", token="secret-token")

    assert repository_in.token_expiration_days is None

    with pytest.raises(ValidationError):
        RepositoryCreate(repository_url="git@github.com:openai/openai-python.git")


def test_repository_schema_serializes_enums_as_strings() -> None:
    repository = Repository(
        name="openai-python",
        repository_url="https://github.com/openai/openai-python.git",
        provider=RepositoryProvider.github,
        owner="openai",
        user_id=uuid.uuid4(),
        status=RepositoryStatus.ready,
    )

    repository_data = RepositoryPublic.model_validate(repository).model_dump(mode="json")

    assert repository_data["provider"] == "github"
    assert repository_data["status"] == "ready"


def test_repository_session_timestamps_are_timezone_aware() -> None:
    session = RepositorySession(owner_id=uuid.uuid4(), repository_id=uuid.uuid4())
    history = SessionHistory(session_id=session.id, role="user", content="query", position=1)

    assert session.created_at.tzinfo is timezone.utc
    assert session.updated_at.tzinfo is timezone.utc
    assert history.created_at.tzinfo is timezone.utc


def test_all_database_models_are_registered() -> None:
    configure_mappers()

    assert {"repository", "repository_session", "session_history", "user"} <= set(SQLModel.metadata.tables)
    assert "branch" not in SQLModel.metadata.tables
    assert "item" not in SQLModel.metadata.tables
    assert "todo" not in SQLModel.metadata.tables
    assert "search_session" not in SQLModel.metadata.tables
    assert "search_history" not in SQLModel.metadata.tables
    assert "memory" not in RepositorySession.model_fields


def test_importing_one_model_registers_all_relationship_targets() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", ("from sqlalchemy.orm import configure_mappers;from app.models.user import User;configure_mappers()")],
        cwd=backend_dir,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_deleting_repository_uses_database_cascade_for_source_documents() -> None:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    user = User(email="owner@example.com", hashed_password="not-used")
    repository = Repository(
        name="openai-python", repository_url="https://github.com/openai/openai-python.git", owner="openai", user_id=user.id, status=RepositoryStatus.ready
    )
    source_document = SourceDocument(repository_id=repository.id, content="print('hello')", doc_metadata={"source": "app/main.py"})

    with Session(engine) as session:
        session.add(user)
        session.add(repository)
        session.add(source_document)
        session.commit()
        session.refresh(repository)
        assert repository.source_documents == [source_document]

        session.delete(repository)
        session.commit()

        assert session.exec(select(SourceDocument).where(SourceDocument.repository_id == repository.id)).all() == []
