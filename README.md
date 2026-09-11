# AI Codebase Copilot

Repository-grounded question answering and an agentic test-generation workflow for Python repositories hosted on GitHub. Connect a GitHub repository, index it, ask questions grounded in its code, and ask the copilot to write tests — reviewed, staticaly by AI review agent, and proposed back to you as a Pull Request once you approve.

> Built on the [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template). This is a course capstone demo, not a production or concurrent system.

## What It Does

1. **Connect a repository** — a public or private GitHub-hosted Python repository, with a mandatory GitHub token used for clone/fetch/push and opening Pull Requests.
2. **Index** — the backend clones the default branch and indexes Python files as vector chunks in Weaviate (hybrid BM25 + vector retrieval, per-user tenancy).
3. **Start a session** — a Repository Session is bound permanently to one repository; its history influences later questions and task planning.
4. **Ask questions** — repository-grounded answers stream back with file-level citations.
5. **Generate tests** — submit a free-text Code Generation Task; a bounded LangGraph workflow plans, retrieves repository documents, generates complete test files, optionally consults web docs for framework syntax, runs the tests in an isolated sandbox, and reviews them.
6. **Review & approve** — progress and the final diff stream over Server-Sent Events; you reject the patch or approve a commit + push to a new non-default branch and the opening of a Pull Request into the default branch.

## Technology Stack

### AI / Retrieval
- 🦜 [**LangChain**](https://python.langchain.com) + [**LangGraph**](https://langchain-ai.github.io/langgraph/) for the agentic code-generation workflow, with a Postgres checkpointer.
- 🧠 LLMs via [Anthropic](https://www.anthropic.com), [OpenAI](https://openai.com), with [Voyage AI](https://www.voyageai.com) (`voyage-code-3`) embeddings and [Cohere](https://cohere.com) reranking.
- 🔎 [**Weaviate**](https://weaviate.io) as the vector database with hybrid BM25 + vector retrieval.
- 🌐 [Tavily](https://tavily.com) web search, reachable only on the code-generation path for test-framework guidance.
- 📊 Optional [LangSmith](https://smith.langchain.com) tracing.

### Backend
- ⚡ [**FastAPI**](https://fastapi.tiangolo.com) with Server-Sent Events for streaming agent progress.
- 🧰 [SQLModel](https://sqlmodel.tiangolo.com) ORM + [Pydantic](https://docs.pydantic.dev), [PostgreSQL](https://www.postgresql.org), [Alembic](https://alembic.sqlalchemy.org) migrations.
- 🐙 [GitPython](https://gitpython.readthedocs.io) for clone/fetch/branch/push and the GitHub API for Pull Requests.
- 🔐 Encrypted-at-rest GitHub tokens, JWT auth, secure password hashing.

### Frontend
- 🚀 [React 19](https://react.dev) + TypeScript, [Vite](https://vitejs.dev), [TanStack Router](https://tanstack.com/router) & [Query](https://tanstack.com/query).
- 🎨 [Tailwind CSS](https://tailwindcss.com) v4 + [shadcn/ui](https://ui.shadcn.com) / Radix, dark mode, an auto-generated API client, and a diff view for proposed patches.
- 🧪 [Playwright](https://playwright.dev) end-to-end tests.

### Infrastructure
- 🐋 [Docker Compose](https://www.docker.com) for development and production (Postgres, Weaviate, Adminer, backend, frontend).
- 📞 [Traefik](https://traefik.io) reverse proxy, CI/CD via GitHub Actions, ✅ [Pytest](https://pytest.org).

## Architecture at a Glance

| Path | Behavior |
| --- | --- |
| **Repository question** | Hybrid retrieval over the session's indexed documents → grounded answer with file citations. Never touches the checkout or web search. |
| **Code Generation Task** | LangGraph run on a temporary branch: classify → plan → retrieve → (research) → generate → execute (sandbox) → review → revise. Bounded by independent **Generation Retries** (default 2) and **Execution Attempts** (default 4). |
| **Patch Review** | The Code Reviewer scores a patch out of 10; the backend decides pass/fail against a threshold (default 7) and hard-fails any patch escaping the test-file boundary. |
| **Approval (HITL)** | A LangGraph interrupt — approve/reject is resumed on the `/questions` endpoint, never a dedicated endpoint. On approval the branch is pushed and a Pull Request is opened carrying the review. |

The single API entry point for questions and tasks is `POST /sessions/{id}/questions`; **Request Intent** is classified there (uncertain classification falls back to a side-effect-free question).

## Repository Configuration

Before connecting a repository, you need a **Fine-grained Personal Access Token (PAT)** from GitHub. The copilot uses it for clone/fetch/push and for opening Pull Requests.

1. Log in to your GitHub account.
2. Visit the GitHub access token screen: <https://github.com/settings/personal-access-tokens>
3. In the left menu go to **Personal access tokens → Fine-grained tokens**, then click **Generate new token**.
4. Under **Repository access**, choose the specific repository (or repositories) you want to grant access to.
5. Under **Permissions**, click **Add permissions** and choose:
   - **Contents**
   - **Pull requests**
6. Set both to **Access: Read and write**.
7. Click **Generate token** and copy it — you'll paste it when creating the repository in the app.

### Recommended configuration

| Setting | Value |
| --- | --- |
| **Resource owner** | Your account or organization |
| **Repository access** | Only select repositories |
| **Contents** | Read and write — *required for clone/push* |
| **Pull requests** | Read and write — *required for creating PRs* |
| **Workflows** | Read and write — *only if modifying workflow files* |
| **Issues** | Read and write |

The token is encrypted at rest with `REPOSITORY_TOKEN_ENCRYPTION_KEY`.

## Getting Started

After cloning this repository, choose Docker Compose for both services or run the backend and frontend locally with their databases in Docker. Run commands from the **repository root** unless a step says otherwise.

### Prerequisites

- Docker with Docker Compose for PostgreSQL, Weaviate, and containerized services.
- For local backend development: Python (the Docker image uses 3.13) and `uv`.
- For local frontend development: Bun (CI uses 1.3.12).

### Configure

If you do not already have a root `.env`, create it:

```bash
cp .env.example .env
```

Edit `.env` and set the required values. Before running, change at least:

- `SECRET_KEY`
- `FIRST_SUPERUSER_PASSWORD`
- `POSTGRES_PASSWORD`
- `REPOSITORY_TOKEN_ENCRYPTION_KEY` — a Fernet key used to encrypt GitHub tokens at rest
- AI provider keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, `COHERE_API_KEY`, `TAVILY_API_KEY`, `HF_TOKEN`

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generate the repository-token encryption (Fernet) key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Pass secrets as environment variables in deployed environments rather than committing them.

### Key Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_MODEL` | `gpt-4o-mini` | Default classification/planning model |
| `LLM_MODEL_STRONG` / `LLM_MODEL_STRONGEST` | `gpt-4o` / `claude-haiku-4-5` | Generation & review models |
| `EMBEDDING_MODEL` | `voyage-code-3` | Code embedding model |
| `COHERE_RERANK_MODEL` | `rerank-v4.0-pro` | Reranker |
| `HYBRID_SEARCH_ALPHA` | `0.3` | BM25 ↔ vector blend |
| `REVIEW_PASS_THRESHOLD` | `7` | Min. patch review score to pass |
| `MAX_GENERATION_RETRIES` | `2` | Revision budget for low-scoring patches |
| `WEAVIATE_HTTP_HOST` / `WEAVIATE_GRPC_HOST` | `localhost` | Weaviate connection |

See [backend/app/core/config.py](./backend/app/core/config.py) for the full set.

### Start both services with Docker Compose

```bash
docker compose up -d --build --wait backend frontend mailcatcher
```

This starts the backend, frontend, and development email service, plus PostgreSQL, Weaviate, and the backend prestart service. Prestart initializes Weaviate, applies database migrations, and creates the first administrator account.

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Interactive API docs: <http://localhost:8000/docs>
- Development email inbox: <http://localhost:1080>

Log in with `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` from your root `.env`.

Inspect startup logs with `docker compose logs -f prestart backend`. For backend source synchronization, run `docker compose watch backend` in another terminal. The Docker frontend serves compiled assets; rebuild it after frontend changes with `docker compose up -d --build frontend`.

### Start the backend locally

In the root `.env`, use the published database addresses:

```dotenv
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
WEAVIATE_HTTP_HOST=localhost
WEAVIATE_HTTP_PORT=8081
WEAVIATE_GRPC_HOST=localhost
WEAVIATE_GRPC_PORT=50051
```

Start the dependencies from the repository root. If the Docker backend is already running, stop it first to free port `8000`:

```bash
docker compose stop backend
docker compose up -d --wait db weaviate
```

Then install dependencies, initialize the databases, and start FastAPI:

```bash
cd backend
uv sync --frozen
uv run bash scripts/prestart.sh
uv run fastapi run --reload --host 127.0.0.1 --port 8000 app/main.py
```

Keep this terminal running. The API is available at <http://localhost:8000/docs>. Run these Python commands from `backend/` so settings load the root `.env` correctly. See [backend/README.md](./backend/README.md) for full configuration, migrations, and tests.

### Start the frontend locally

With the backend running locally or in Docker, open a separate terminal at the repository root. Stop the Docker frontend if it is running to free port `5173`, then install dependencies:

```bash
docker compose stop frontend
bun install
```

Set the following entry in `frontend/.env` (a separate file from the root `.env`):

```dotenv
VITE_API_URL=http://localhost:8000
```

Start the Vite development server from the repository root:

```bash
bun run dev
```

Open <http://localhost:5173>. Use the backend origin without `/api/v1` for `VITE_API_URL`, and restart Vite after changing it. See [frontend/README.md](./frontend/README.md) for builds, API client generation, and end-to-end tests.

## Development

- Project overview, architecture, and workflows: [PROJECT.md](./PROJECT.md)
- Backend docs: [backend/README.md](./backend/README.md)
- Frontend docs: [frontend/README.md](./frontend/README.md)
- General development (Docker Compose, local domains, `.env`): [development.md](./development.md)
- Deployment: [deployment.md](./deployment.md)

A Postman collection is available under [postman/](./postman/).

## License

Licensed under the terms of the MIT license. Built on the Full Stack FastAPI Template.
