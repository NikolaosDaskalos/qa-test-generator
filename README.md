# AI Codebase Copilot

Repository-grounded question answering and an agentic test-generation workflow for Python repositories hosted on GitHub. Connect a GitHub repository, index it, ask questions grounded in its code, and ask the copilot to write tests — reviewed, executed in a sandbox, and proposed back to you as a Pull Request once you approve.

> Built on the [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template). This is a course capstone demo, not a production or concurrent system. See [CONTEXT.md](./CONTEXT.md) for the full domain language and [docs/backend-plan.md](./docs/backend-plan.md) for the backend plan.

## What It Does

1. **Connect a repository** — a public or private GitHub-hosted Python repository, with a mandatory GitHub token used for clone/fetch/push and opening Pull Requests.
2. **Index** — the backend clones the default branch and indexes Python files as vector chunks in Weaviate (hybrid BM25 + vector retrieval, per-user tenancy).
3. **Start a session** — a Repository Session is bound permanently to one repository; its history influences later questions and task planning.
4. **Ask questions** — repository-grounded answers stream back with file-level citations.
5. **Generate tests** — submit a free-text Code Generation Task; a bounded LangGraph workflow plans, retrieves repository documents, generates complete test files, optionally consults web docs for framework syntax, runs the tests in an isolated sandbox, and reviews them.
6. **Review & approve** — progress and the final diff stream over Server-Sent Events; you reject the patch or approve a commit + push to a new non-default branch and the opening of a Pull Request into the default branch.
7. **Sync** — a manual endpoint incrementally re-indexes only the files changed since the last indexed commit.

Out of scope for the demo: GitLab/Bitbucket, non-Python repositories, automatic/webhook sync, concurrent coding runs, application-code changes, and backend-side merges.

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

You can **clone** this repository and run it with Docker Compose.

### Configure

Copy `.env.example` to `.env` and set the required values. Before running, change at least:

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

### Run

```bash
docker compose watch
```

This starts Postgres, Weaviate, Adminer, the backend, and the frontend. The frontend is served at `http://localhost:5173` and the API at `http://localhost:8000` (interactive docs at `http://localhost:8000/docs`).

## Development

- Backend docs: [backend/README.md](./backend/README.md)
- Frontend docs: [frontend/README.md](./frontend/README.md)
- General development (Docker Compose, local domains, `.env`): [development.md](./development.md)
- Deployment: [deployment.md](./deployment.md)
- Domain language: [CONTEXT.md](./CONTEXT.md) · Backend plan: [docs/backend-plan.md](./docs/backend-plan.md)

A Postman collection is available under [postman/](./postman/).

## License

Licensed under the terms of the MIT license. Built on the Full Stack FastAPI Template.
