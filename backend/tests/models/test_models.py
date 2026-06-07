import subprocess
import sys
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import configure_mappers
from sqlmodel import SQLModel

from app.models.branch import Branch
from app.models.git_repositories import GitRepository, GitRepositoryCreate
from app.models.searches import SearchHistory, SearchSession


def test_repository_token_fields_are_on_repository() -> None:
    assert "encrypted_token" in GitRepository.model_fields
    assert "token_expiration_date" in GitRepository.model_fields


def test_repository_create_requires_token_and_allows_no_expiration() -> None:
    repository = GitRepositoryCreate(
        repository_url="git@github.com:openai/openai-python.git",
        token="secret-token",
    )

    assert repository.token_expiration_days is None

    with pytest.raises(ValidationError):
        GitRepositoryCreate(
            repository_url="git@github.com:openai/openai-python.git"
        )


def test_search_timestamps_are_timezone_aware() -> None:
    session = SearchSession(owner_id=uuid.uuid4())
    history = SearchHistory(
        session_id=session.id,
        owner_id=session.owner_id,
        query="query",
    )

    assert session.created_at.tzinfo is timezone.utc
    assert session.updated_at.tzinfo is timezone.utc
    assert history.created_at.tzinfo is timezone.utc


def test_all_database_models_are_registered() -> None:
    configure_mappers()

    assert {
        "branch",
        "git_repository",
        "item",
        "search_history",
        "search_session",
        "todo",
        "user",
    } <= set(SQLModel.metadata.tables)
    branch_table = cast(Any, Branch).__table__
    assert branch_table.c.git_repository_id.foreign_keys


def test_importing_one_model_registers_all_relationship_targets() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from sqlalchemy.orm import configure_mappers;"
                "from app.models.users import User;"
                "configure_mappers()"
            ),
        ],
        cwd=backend_dir,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
