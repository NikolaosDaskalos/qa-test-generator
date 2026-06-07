from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings


def build_settings(tmp_path: Path, **updates: Any) -> Settings:
    values: dict[str, Any] = {
        "PROJECT_NAME": "Test Project",
        "SECRET_KEY": "test-secret",
        "ENVIRONMENT": "production",
        "POSTGRES_SERVER": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "test-password",
        "POSTGRES_DB": "test",
        "FIRST_SUPERUSER": "admin@example.com",
        "FIRST_SUPERUSER_PASSWORD": "test-password",
        "OPENAI_API_KEY": "test",
        "ANTHROPIC_API_KEY": "test",
        "TAVILY_API_KEY": "test",
        "VOYAGE_API_KEY": "test",
        "HF_TOKEN": "test",
        "CHROMA_DB_PATH": tmp_path / "chroma",
        "REPO_PATH": tmp_path / "repositories",
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def test_deployment_accepts_valid_repository_token_encryption_key(
    tmp_path: Path,
) -> None:
    encryption_key = Fernet.generate_key().decode()

    configured = build_settings(
        tmp_path,
        REPOSITORY_TOKEN_ENCRYPTION_KEY=encryption_key,
    )

    assert configured.repository_token_encryption_key == encryption_key.encode()


def test_deployment_rejects_invalid_repository_token_encryption_key(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValidationError,
        match="REPOSITORY_TOKEN_ENCRYPTION_KEY must be a valid Fernet key",
    ):
        build_settings(
            tmp_path,
            REPOSITORY_TOKEN_ENCRYPTION_KEY="ordinary-secret",
        )
