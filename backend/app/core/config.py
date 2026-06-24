"""Define application settings and environment-value normalization."""

import os
import secrets
import warnings
from base64 import urlsafe_b64encode
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal

from cryptography.fernet import Fernet
from pydantic import AnyUrl, BeforeValidator, EmailStr, Field, HttpUrl, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

PROJECT_PATH = Path(__file__).resolve().parents[3]


def parse_cors(v: Any) -> list[str] | str:
    """Normalize comma-separated or JSON-style CORS origin settings.

    Raises:
        ValueError: If the value is neither a string nor a list.

    """
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    """Load and validate runtime configuration from environment sources."""

    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_file_override=True,
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    REPOSITORY_TOKEN_ENCRYPTION_KEY: str | None = None
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """Return normalized backend and frontend CORS origins."""
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        """Build the PostgreSQL connection URI from database settings."""
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        """Use the project name as the default email sender name."""
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        """Return whether enough SMTP settings exist to send email."""
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        """Reject placeholder secrets outside local development."""
        if value == "changethis":
            message = f'The value of {var_name} is "changethis", for security, please change it, at least for deployments.'
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        """Validate deployment secrets and repository token encryption."""
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret("FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD)

        if self.ENVIRONMENT != "local" and not self.REPOSITORY_TOKEN_ENCRYPTION_KEY:
            raise ValueError("REPOSITORY_TOKEN_ENCRYPTION_KEY must be configured outside local development")

        if self.REPOSITORY_TOKEN_ENCRYPTION_KEY:
            try:
                Fernet(self.REPOSITORY_TOKEN_ENCRYPTION_KEY.encode())
            except ValueError as exc:
                raise ValueError("REPOSITORY_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

        return self

    @property
    def repository_token_encryption_key(self) -> bytes:
        """Return the configured key or a stable local-development key."""
        if self.REPOSITORY_TOKEN_ENCRYPTION_KEY:
            return self.REPOSITORY_TOKEN_ENCRYPTION_KEY.encode()

        # Local development uses a stable derived key. Deployed environments
        # must configure a dedicated encryption key.
        return urlsafe_b64encode(sha256(self.SECRET_KEY.encode()).digest())

    OPENAI_API_KEY: str
    COHERE_API_KEY: str
    ANTHROPIC_API_KEY: str
    TAVILY_API_KEY: str
    VOYAGE_API_KEY: str
    HF_TOKEN: str

    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MODEL_STRONGEST: str = "claude-haiku-4-5"
    LLM_MODEL_STRONG: str = "gpt-4o"

    LLM_MAX_TOKENS: int = 2000
    STRONG_LLM_MAX_TOKENS: int = 7000
    STRONGEST_LLM_MAX_TOKENS: int = 7000
    TEMPERATURE: float = 0.0

    # Cross-provider fallback for the Code Reviewer (ADR 0010): the primary reviewer is
    # the Anthropic STRONGEST model; on a transient failure it falls over to this OpenAI
    # model so a single-provider blip no longer fails a Coding Run. max_tokens mirrors the
    # existing *_MAX_TOKENS pattern; TEMPERATURE stays 0.0 across every model.
    REVIEWER_FALLBACK_LLM_MODEL: str = "gpt-4o-mini"
    REVIEWER_FALLBACK_LLM_MAX_TOKENS: int = 7000

    # Cross-provider fallback for direct default-tier calls (ADR 0010): the
    # classifier, planner, and repository-question answerer run OpenAI
    # gpt-4o-mini first; on a transient failure they fall over to Anthropic
    # Claude Haiku. The token budget mirrors LLM_MAX_TOKENS.
    DEFAULT_LLM_FALLBACK_MODEL: str = "claude-haiku-4-5"
    DEFAULT_LLM_FALLBACK_MAX_TOKENS: int = 2000

    # Cross-provider fallback for the Code Generator's strong tier (ADR 0010): the
    # primary generator is OpenAI gpt-4o; on a transient failure it falls over to
    # Anthropic Claude Sonnet. The token budget mirrors STRONG_LLM_MAX_TOKENS.
    STRONG_LLM_FALLBACK_MODEL: str = "claude-sonnet-4-6"
    STRONG_LLM_FALLBACK_MAX_TOKENS: int = 7000

    # SDK-level bounded retry budget applied on each chat-model constructor, using the
    # provider SDK's built-in exponential backoff, before any cross-provider fallback fires.
    LLM_MAX_RETRIES: int = Field(default=3, ge=0)

    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "qa-test-generator"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    EMBEDDING_MODEL: str = "voyage-code-3"
    EMBEDDING_MODEL_TOKENIZER: str = "voyageai/voyage-code-3"
    EMBEDDING_DIMENSIONS: Literal[256, 512, 1024, 2048] = 1024

    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 10
    TOP_K: int = Field(default=10, ge=1)
    FINAL_PARENT_LIMIT: int = Field(default=5, ge=1)
    # Multi-query + RAG-fusion on the simple repository-question strategy: how many query
    # reformulations to generate (N), and the Reciprocal Rank Fusion rank constant (k).
    QUERY_VARIANT_COUNT: int = Field(default=3, ge=1)
    RRF_K: int = Field(default=60, ge=1)
    COHERE_RERANK_MODEL: str = "rerank-v4.0-pro"

    WEAVIATE_HTTP_HOST: str = "localhost"
    WEAVIATE_HTTP_PORT: int = 8081
    WEAVIATE_HTTP_SECURE: bool = False
    WEAVIATE_GRPC_HOST: str = "localhost"
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_GRPC_SECURE: bool = False
    WEAVIATE_API_KEY: str | None = None
    WEAVIATE_COLLECTION: str = "Document"
    # alpha value:
    # - 1.0 -> Pure vector search
    # - 0.0 -> pure BM25 search
    HYBRID_SEARCH_ALPHA: float = Field(default=0.3, ge=0.0, le=1.0)

    # Max connections in the shared PostgresSaver pool backing the session graph checkpointer.
    CHECKPOINTER_POOL_MAX_SIZE: int = Field(default=10, ge=1)

    SESSION_HISTORY_LIMIT: int = 10
    RECURSION_LIMIT: int = 7

    # The Patch Review pass bar: a patch is accepted when its reviewer score (0–10)
    # meets this threshold. The backend owns this decision; the reviewer only scores.
    REVIEW_PASS_THRESHOLD: int = Field(default=7, ge=0, le=10)

    # Generation Retries: how many times the Code Generator may revise a below-threshold
    # Test Patch before the post-review router escalates the best attempt to human review.
    # Exhaustion escalates, never fails. Zero disables revision entirely.
    MAX_GENERATION_RETRIES: int = Field(default=2, ge=0)

    REPO_PATH: Path = Field(default_factory=lambda: PROJECT_PATH / ".tmp/repositories")

    # The GitHub REST API base URL used when opening a Pull Request on Approval.
    # Defaults to public GitHub; override for a GitHub Enterprise Server install.
    GITHUB_API_BASE_URL: str = "https://api.github.com"

    def model_post_init(self, __context) -> None:
        """Create the local repository storage directory and wire LangSmith tracing."""
        self.REPO_PATH.mkdir(parents=True, exist_ok=True)
        self._configure_langsmith()

    def _configure_langsmith(self) -> None:
        """Mirror LangSmith settings into ``os.environ`` for LangChain auto-tracing.

        LangChain/LangGraph read tracing config straight from the process environment,
        but pydantic loads the ``.env`` file without exporting it there. When tracing is
        disabled or no API key is set we leave the environment untouched so a stray
        ``LANGSMITH_TRACING`` never silently turns tracing on without credentials.
        """
        if self.LANGSMITH_TRACING and self.LANGSMITH_API_KEY:
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGSMITH_PROJECT"] = self.LANGSMITH_PROJECT
            os.environ["LANGSMITH_ENDPOINT"] = self.LANGSMITH_ENDPOINT

        if self.HF_TOKEN:
            os.environ["HF_TOKEN"] = self.HF_TOKEN

    @classmethod
    def settings_customise_sources(
            cls, settings_cls: type[BaseSettings], init_settings: Any, env_settings: Any, dotenv_settings: Any, file_secret_settings: Any
    ) -> tuple[Any, ...]:
        """Prioritize dotenv values over process environment variables."""
        # .env file takes priority over system/process environment variables
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)


settings = Settings()  # type: ignore
