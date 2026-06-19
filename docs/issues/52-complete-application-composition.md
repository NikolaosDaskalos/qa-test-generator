# Complete application composition and shared infrastructure

Status: completed
Type: AFK
User stories: None - structural refactor preserving existing authenticated behavior

## What to build

Complete the feature-oriented FastAPI structure after the Repository, Repository Session, Coding Run, agents, and RAG moves. Give database setup, concrete external integrations, application configuration, security, lifecycle management, authentication persistence, and dependency composition predictable homes without creating new behavior.

The final structure must keep `agents` and `rag` explicit, keep `core` limited to genuinely application-wide concerns, and make dependency direction visible and enforceable.

## Acceptance criteria

- [x] Database session setup, records, and persistence adapters have one predictable `db` structure without duplicate legacy modules.
- [x] Concrete Git, Weaviate, LLM, and web-search clients have explicit integration placement while LangChain agents remain under `agents` and RAG behavior remains under `rag`.
- [x] `core` contains only shared configuration, security, exceptions, and application lifecycle concerns.
- [x] FastAPI dependency providers and application startup form a clear composition root with no request-scoped resources captured by background work.
- [x] Authentication, users, email utilities, startup checks, migrations, and generated contracts continue to work through their final imports.
- [x] Legacy pass-through packages and compatibility re-exports are removed after all callers migrate.
- [x] Automated import-direction checks prevent HTTP or infrastructure concerns from leaking back into feature workflows.
- [x] The complete backend and frontend regression suites pass without endpoint, persistence, Agent Stream, or user-visible behavior changes.

## Blocked by

- [Issue 49](49-reorganize-repository-lifecycle.md)
- [Issue 50](50-reorganize-repository-sessions.md)
- [Issue 51](51-separate-coding-runs-from-ai-agents.md)
