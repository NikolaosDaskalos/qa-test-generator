"""Test application configuration defaults and secret validation."""

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import PROJECT_PATH, Settings


def build_settings(tmp_path: Path, **updates: Any) -> Settings:
    """Build isolated production settings with optional overrides."""
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
        "COHERE_API_KEY": "test",
        "ANTHROPIC_API_KEY": "test",
        "TAVILY_API_KEY": "test",
        "VOYAGE_API_KEY": "test",
        "HF_TOKEN": "test",
        "REPO_PATH": tmp_path / "repositories",
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def test_default_repository_path_is_outside_backend() -> None:
    """Store cloned repositories outside the backend package tree."""
    default_path = Settings.model_fields["REPO_PATH"].get_default(call_default_factory=True)

    assert default_path == PROJECT_PATH / ".tmp/repositories"


def test_deployment_accepts_valid_repository_token_encryption_key(tmp_path: Path) -> None:
    """Accept a valid Fernet key in deployed environments."""
    encryption_key = Fernet.generate_key().decode()

    configured = build_settings(tmp_path, REPOSITORY_TOKEN_ENCRYPTION_KEY=encryption_key)

    assert configured.repository_token_encryption_key == encryption_key.encode()


def test_deployment_rejects_invalid_repository_token_encryption_key(tmp_path: Path) -> None:
    """Reject malformed repository encryption keys in deployments."""
    with pytest.raises(ValidationError, match="REPOSITORY_TOKEN_ENCRYPTION_KEY must be a valid Fernet key"):
        build_settings(tmp_path, REPOSITORY_TOKEN_ENCRYPTION_KEY="ordinary-secret")


def test_reranking_configuration_is_independent_of_candidate_count(tmp_path: Path) -> None:
    """Configure Cohere and the final parent limit independently of candidate retrieval."""
    configured = build_settings(
        tmp_path,
        COHERE_API_KEY="cohere-test-key",
        COHERE_RERANK_MODEL="rerank-test-model",
        TOP_K=12,
        FINAL_PARENT_LIMIT=4,
        REPOSITORY_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )

    assert configured.COHERE_API_KEY == "cohere-test-key"
    assert configured.COHERE_RERANK_MODEL == "rerank-test-model"
    assert configured.TOP_K == 12
    assert configured.FINAL_PARENT_LIMIT == 4
