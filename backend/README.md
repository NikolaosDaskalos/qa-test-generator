# Backend service

The FastAPI application is defined in [app/main.py](app/main.py). It uses PostgreSQL for application data and session checkpoints, and Weaviate for repository document retrieval. This guide describes the checked-in implementation; configuration defaults below come from [Settings](app/core/config.py), not from example credentials.

## Requirements

- Python and `uv` for running on the host. [pyproject.toml](pyproject.toml) declares Python `>=3.10,<4.0`; the [Dockerfile](Dockerfile) uses Python 3.13.
- Docker with Compose for the supplied infrastructure or containerized backend. [compose.yml](../compose.yml) uses PostgreSQL 18 and Weaviate 1.37.4.
- Credentials for the providers listed below.

The backend belongs to the root [uv workspace](../pyproject.toml), which shares the root `uv.lock` and `.venv`. Run backend Python and Alembic commands from `backend/` so the relative settings and migration paths resolve correctly.

## Configuration

Create a repository-root `.env` from [.env.example](../.env.example) if one does not already exist. Edit the copy before starting the service: the example leaves required provider credentials empty and includes example secrets.

[Settings](app/core/config.py) is instantiated at import time. Its source priority is constructor arguments, `../.env`, process environment, file secrets, then field defaults. **A nonempty `.env` value overrides an exported shell variable.** Empty environment values are ignored and unknown keys are ignored. On the host, `../.env` resolves relative to the working directory, hence the commands below use `backend/`.

Compose passes the root `.env` through `env_file` and overrides container connection addresses in `environment`. The Dockerfile does not copy `.env` into the image.

### Required values

These fields have no default; missing or empty values cause settings validation to fail, even if the corresponding feature is not used immediately.

| Variable | Purpose |
| --- | --- |
| `PROJECT_NAME` | FastAPI title and default email sender name |
| `POSTGRES_SERVER`, `POSTGRES_USER` | Database host and login |
| `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD` | Initial administrator email and password |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Primary and fallback chat models |
| `COHERE_API_KEY` | Retrieval reranking |
| `TAVILY_API_KEY` | Web search |
| `VOYAGE_API_KEY` | Repository embeddings |
| `HF_TOKEN` | Hugging Face tokenizer access; copied into the process environment |

Provider usage is implemented in [llm.py](app/integrations/llm.py), [web_search.py](app/integrations/web_search.py), [Weaviate resources](app/integrations/weaviate/resources.py), and the [ingestor](app/rag/ingestor.py). Settings validation checks presence/types, not whether provider credentials work.

### Application, database, and secrets

| Variable | Code default / behavior |
| --- | --- |
| `ENVIRONMENT` | `local`; also accepts `staging` and `production`. Private API routes are included only in `local`. |
| `API_V1_STR` | `/api/v1` |
| `FRONTEND_HOST` | `http://localhost:5173`; also added to allowed CORS origins |
| `BACKEND_CORS_ORIGINS` | Empty list; accepts comma-separated origins or a JSON list |
| `SECRET_KEY` | Random `secrets.token_urlsafe(32)` value when omitted; configure a stable value across restarts and workers for JWT signing |
| `REPOSITORY_TOKEN_ENCRYPTION_KEY` | Unset; must be a valid Fernet key when supplied and is required outside `local`. Locally, omission derives a key from `SECRET_KEY`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `11520` (8 days) |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_PASSWORD`, `POSTGRES_DB` | Empty strings in code; set both for the supplied PostgreSQL Compose service |
| `CHECKPOINTER_POOL_MAX_SIZE` | `10`, minimum `1`; maximum connections per process for the session checkpoint pool |
| `REPO_PATH` | `<repository root>/.tmp/repositories` on the host, `/app/.tmp/repositories` in the image; created when settings load |
| `GITHUB_API_BASE_URL` | `https://api.github.com`; configurable for GitHub Enterprise Server |

The database URL is computed from the `POSTGRES_*` fields with the `postgresql+psycopg` scheme; there is no separate database-URL setting. The literal `changethis` for `SECRET_KEY`, `POSTGRES_PASSWORD`, or `FIRST_SUPERUSER_PASSWORD` emits a warning locally and fails validation in staging/production. See [config.py](app/core/config.py), [security.py](app/core/security.py), and [API routing](app/api/main.py).

After installing dependencies, generate values from `backend/` and save them in `.env`:

```bash
uv run python -c 'import secrets; print(secrets.token_urlsafe(32))'
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

The supplied Compose files persist PostgreSQL and Weaviate data in named volumes. They do not mount a persistent volume for `REPO_PATH`; configure one if repository checkouts must survive container replacement.

### Weaviate and retrieval

Both HTTP and gRPC must be reachable. [client.py](app/integrations/weaviate/client.py) uses the following connection settings:

| Variable | Code default |
| --- | --- |
| `WEAVIATE_HTTP_HOST`, `WEAVIATE_HTTP_PORT`, `WEAVIATE_HTTP_SECURE` | `localhost`, `8081`, `false` |
| `WEAVIATE_GRPC_HOST`, `WEAVIATE_GRPC_PORT`, `WEAVIATE_GRPC_SECURE` | `localhost`, `50051`, `false` |
| `WEAVIATE_API_KEY` | Unset; adds API-key authentication when supplied |
| `WEAVIATE_COLLECTION` | `Document` |
| `EMBEDDING_MODEL`, `EMBEDDING_MODEL_TOKENIZER` | `voyage-code-3`, `voyageai/voyage-code-3` |
| `EMBEDDING_DIMENSIONS` | `1024`; accepts `256`, `512`, `1024`, `2048` |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | `500`, `10` |
| `MAX_INGEST_FILE_BYTES` | `1000000`, minimum `1` |
| `TOP_K`, `FINAL_PARENT_LIMIT` | `10`, `5`; each at least `1` |
| `HYBRID_SEARCH_ALPHA` | `0.3`, range `0`–`1`; `0` is BM25, `1` is vector search |
| `COHERE_RERANK_MODEL` | `rerank-v4.0-pro` |
| `QUERY_VARIANT_COUNT`, `RRF_K`, `MAX_SUB_QUESTIONS` | `3`, `60`, `3`; each at least `1` |

The checked-in `.env.example` overrides `HYBRID_SEARCH_ALPHA` to `0.7` and `COHERE_RERANK_MODEL` to `rerank-v4.0-fast`. The supplied Weaviate container enables anonymous access; its HTTP port is `8080` internally and `8081` on the host.

### Chat models and session behavior

Defaults are declared in [config.py](app/core/config.py); model/provider wiring is in [dependencies.py](app/api/dependencies.py).

| Model setting | Code default | Token-budget setting (default) |
| --- | --- | --- |
| `LLM_MODEL` | `gpt-4o-mini` (OpenAI) | `LLM_MAX_TOKENS` (`2000`) |
| `LLM_MODEL_STRONG` | `gpt-4o` (OpenAI) | `STRONG_LLM_MAX_TOKENS` (`7000`) |
| `LLM_MODEL_STRONGEST` | `claude-haiku-4-5` (Anthropic) | `STRONGEST_LLM_MAX_TOKENS` (`7000`) |
| `DEFAULT_LLM_FALLBACK_MODEL` | `claude-haiku-4-5` (Anthropic) | `DEFAULT_LLM_FALLBACK_MAX_TOKENS` (`2000`) |
| `STRONG_LLM_FALLBACK_MODEL` | `claude-sonnet-4-6` (Anthropic) | `STRONG_LLM_FALLBACK_MAX_TOKENS` (`7000`) |
| `REVIEWER_FALLBACK_LLM_MODEL` | `gpt-4o-mini` (OpenAI) | `REVIEWER_FALLBACK_LLM_MAX_TOKENS` (`7000`) |

`TEMPERATURE` defaults to `0.0`. `LLM_MAX_RETRIES` defaults to `3` (minimum `0`) for each provider SDK. Model names configure the wired provider; changing a name does not switch the client to another provider.

| Variable | Code default / meaning |
| --- | --- |
| `SESSION_HISTORY_LIMIT` | `10`; recent messages supplied to AI context |
| `SESSION_HISTORY_PAGE_SIZE` | `50`; history display page size |
| `RECURSION_LIMIT` | `7`; graph recursion limit |
| `track_costs` | `true`; usage capture setting |
| `REVIEW_PASS_THRESHOLD` | `7`, range `0`–`10`; patch review acceptance threshold |
| `MAX_GENERATION_RETRIES` | `2`, minimum `0`; revisions before escalation to human review; `0` disables revisions |

### Email and observability

These defaults are defined in [config.py](app/core/config.py); email delivery is implemented in [email.py](app/integrations/email.py).

| Variable | Code default / behavior |
| --- | --- |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAILS_FROM_EMAIL` | Unset; email is enabled when host and sender address are both set |
| `SMTP_PORT`, `SMTP_TLS`, `SMTP_SSL` | `587`, `true`, `false` |
| `EMAILS_FROM_NAME` | Falls back to `PROJECT_NAME` |
| `EMAIL_RESET_TOKEN_EXPIRE_HOURS` | `48` |
| `EMAIL_TEST_USER` | `test@example.com` |
| `SENTRY_DSN` | Unset; [main.py](app/main.py) initializes Sentry only when supplied outside `local` |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` | `false`, unset; settings export tracing configuration when tracing is enabled and a key is supplied |
| `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT` | `qa-test-generator`, `https://api.smith.langchain.com` |

The development Compose override directs backend email to `mailcatcher:1025`, disables SMTP TLS, and sets the sender to `noreply@example.com`. Its inbox UI is exposed at `http://localhost:1080`.

## Start with Docker Compose

Run these commands from the **repository root**, after configuring `.env`. Compose also requires its interpolation variables, including `DOMAIN`, `STACK_NAME`, `DOCKER_IMAGE_BACKEND`, `DOCKER_IMAGE_FRONTEND`, `FRONTEND_HOST`, and the database/admin/secret values supplied by the example.

```bash
docker compose up -d --build backend mailcatcher
docker compose logs -f prestart backend
```

This starts the backend and its PostgreSQL, Weaviate, and prestart dependencies, plus the development email service. The default [development override](../compose.override.yml) exposes the backend on port `8000` and runs `fastapi run --reload app/main.py`. To synchronize host edits into the running container, run from the root in another terminal:

```bash
docker compose watch backend
```

Watch syncs `backend/` to `/app/backend` and rebuilds when `backend/pyproject.toml` changes. Without the override, the [Dockerfile](Dockerfile) starts `fastapi run --workers 4 app/main.py`. Compose overrides `POSTGRES_SERVER=db`, `WEAVIATE_HTTP_HOST=weaviate`, `WEAVIATE_HTTP_PORT=8080`, and `WEAVIATE_GRPC_HOST=weaviate` for backend and prestart containers.

## Start the backend on the host

Use the root `.env` with `POSTGRES_SERVER=localhost`, `POSTGRES_PORT=5432`, `WEAVIATE_HTTP_HOST=localhost`, `WEAVIATE_HTTP_PORT=8081`, `WEAVIATE_GRPC_HOST=localhost`, and `WEAVIATE_GRPC_PORT=50051` for the supplied published ports.

From the **repository root**, start the infrastructure:

```bash
docker compose up -d db weaviate
```

Then install, initialize, and start from **backend/**:

```bash
cd backend
uv sync --frozen
uv run bash scripts/prestart.sh
uv run fastapi run --reload --host 127.0.0.1 --port 8000 app/main.py
```

If a containerized backend already occupies port `8000`, stop it with `docker compose stop backend` from the root before starting the host process. For an editor interpreter, use `<repository root>/.venv/bin/python`.

### What initialization does

[scripts/prestart.sh](scripts/prestart.sh) exits on failure and runs these steps in order:

1. [backend_pre_start.py](app/scripts/backend_pre_start.py) checks PostgreSQL, then connects to Weaviate. Each readiness operation retries up to 300 attempts with a one-second wait. It creates the configured collection if absent and validates multi-tenancy, text metadata properties, and self-provided vectors on existing collections.
2. `alembic upgrade head` applies application migrations.
3. [initial_data.py](app/scripts/initial_data.py) calls [init_db](app/db/seed.py) to create the configured first superuser if that email does not exist. Rerunning it does not reset an existing user's password.

Compose waits for healthy PostgreSQL/Weaviate services and successful prestart completion before starting the backend. Running FastAPI directly does **not** execute this prestart script.

At application startup, [lifespan](app/main.py) initializes the shared Weaviate client/vector store and opens the [PostgreSQL checkpointer](app/core/checkpointer.py), whose `setup()` provisions checkpoint tables separately from Alembic. Each worker owns its resources; normal shutdown closes the checkpointer pool and Weaviate client. Startup therefore needs both backing services available.

### Verify startup

With the default API prefix and port:

```bash
curl --fail http://localhost:8000/api/v1/utils/health-check/
```

The [health endpoint](app/api/routes/utils.py) returns JSON `true`; it does not query dependencies or validate provider credentials. OpenAPI is available at `http://localhost:8000/api/v1/openapi.json`, and Swagger UI at `http://localhost:8000/docs`.

The Compose healthcheck hardcodes `/api/v1/utils/health-check/`; update it too if changing `API_V1_STR`. If initialization fails, inspect prestart logs for missing settings, database connectivity, or an incompatible Weaviate collection before restarting.

## Development and migrations

API endpoints live in [app/api/](app/api/), SQLModel records in [app/db/models/](app/db/models/), and database adapters in [app/db/persistence/](app/db/persistence/). `Repository` refers to a registered source repository; persistence adapters use `Store` names.

[Alembic's environment](app/alembic/env.py) imports database models and uses `SQLModel.metadata` and the configured database URL. From **backend/**, after changing models:

```bash
uv run alembic revision --autogenerate -m "Describe the schema change"
uv run alembic upgrade head
```

Review and commit generated files under `app/alembic/versions/`. Generate revisions on the host: Compose watch synchronizes host files into the container, and generated container files are not written back by that sync configuration.

## Tests

Use a disposable, migrated database: the [test fixtures](tests/conftest.py) seed data and delete users during teardown. With configuration and backing services ready, run from **backend/**:

```bash
uv run bash scripts/tests-start.sh
```

[tests-start.sh](scripts/tests-start.sh) checks database readiness, then [test.sh](scripts/test.sh) runs the suite with coverage and writes `htmlcov/index.html`. It does not apply migrations. Extra script arguments become the coverage HTML title, not pytest options. To pass pytest options directly:

```bash
uv run pytest tests/ -x
```

For an initialized container stack, run from the root:

```bash
docker compose exec backend bash scripts/tests-start.sh
```

## Email templates

[app/integrations/email-templates/src/](app/integrations/email-templates/src/) contains MJML sources. [app/integrations/email-templates/build/](app/integrations/email-templates/build/) contains the HTML templates loaded by [email.py](app/integrations/email.py).
