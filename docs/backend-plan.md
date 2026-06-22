# Backend Demo Plan

## Goal

Demonstrate repository-grounded RAG and a bounded LangGraph code-generation workflow using FastAPI, LangChain, Weaviate, Git, and an LLM. This is a course demo, not a production or concurrent system.

## Demo Journey

1. A user connects a public or private GitHub-hosted Python repository with a mandatory token.
2. The backend clones its default branch and indexes Python files in Weaviate.
3. The user creates a repository session bound permanently to that repository.
4. The user asks codebase questions and receives repository-grounded answers with file citations.
5. The user submits a free-text Code Generation Task.
6. A LangGraph workflow plans, retrieves Repository Documents, generates complete test files, reviews them, and uses bounded Generation Retries when needed.
7. The backend streams progress and the final diff through server-sent events.
8. The user rejects the patch or approves a commit and push to a new non-default branch.

Pull-request creation, GitHub Actions integration, local test execution, dependency installation, GraphRAG, multiple languages, multiple providers, webhooks, scheduling, and concurrent coding runs are outside the demo scope.

## Repository Lifecycle

- Accept GitHub URLs only.
- Support both public and private GitHub repositories.
- Require a GitHub token for every repository.
- Clone the default branch into the existing user-isolated checkout.
- Record the current indexed commit SHA.
- Run clone, initial indexing, and synchronization as FastAPI background tasks.
- Permit at most one active coding run per repository.

### Incremental Synchronization

Expose a manual `POST /repositories/{id}/sync` endpoint. Fetch the latest default branch and use:

```text
git diff --name-status -M <indexed_sha>..<latest_sha>
```

Apply file-level vector changes:

- `A`: index the new Python file.
- `M`: delete and re-index all chunks for the file.
- `D`: delete all chunks for the file.
- `R`: delete chunks under the old path and index the renamed file.

Advance `indexed_commit_sha` only after every vector operation succeeds. Expose synchronization status and a sanitized failure reason.

## Indexing And Retrieval

- Use the existing Python-aware recursive splitter.
- Store `repository_id`, `commit_sha`, `source`, and `parent_id` on every chunk.
- Keep Weaviate tenancy per user.
- Require a `repository_id` filter on every retrieval query.
- Return file-level citations; symbol extraction and line-level citations are not required.
- Use hybrid BM25 and vector retrieval through Weaviate.
- Reranking and GraphRAG are optional extensions, not MVP requirements.

## Repository Questions

- A repository session requires `repository_id` and cannot switch repositories.
- Persist each exchange as session history.
- Use at most the six latest history messages for reformulation.
- Remove the duplicate JSON memory field from the session model.
- Answer codebase questions only from Repository Documents.
- If the retrieved Repository Documents are insufficient, state that the Repository does not provide enough information.
- Tavily may run only when the user explicitly requests documentation, best practices, or external guidance.
- Present repository sources and external references as separate groups.

Question endpoints use a synchronous SSE response for stage updates, answer tokens, citations, and the final persisted result.

## Code-Generation Graph

Use a bounded LangGraph workflow:

```text
plan
  -> retrieve repository context
  -> generate test patch
  -> review patch
  -> retry generation while below threshold and Generation Retries remain
  -> review patch
  -> await human approval
```

The planner emits Retrieval Requests and optional candidate paths. Candidate paths are hints only; the backend validates them and retrieval supplies the actual Repository Documents. The LLM receives no unrestricted filesystem tool.

The code generator returns complete file contents:

```json
{
  "files": [
    {
      "path": "tests/services/test_auth.py",
      "content": "...complete file content..."
    }
  ]
}
```

The backend validates and writes the files, then derives the unified diff with Git.

### Patch Validation

Permit:

- Existing Python files already recognized as tests.
- New `.py` files inside an existing `tests/` or `test/` root.

Reject:

- Paths outside the checkout.
- Symlinks.
- Non-Python files.
- Application or source files.
- A newly invented test root.

The Code Reviewer checks task alignment, repository conventions, imports visible in Repository Documents, unrelated changes, and whether only test files changed. Tests are not executed and dependencies are not installed.

## Checkout And Approval

Use the single existing checkout rather than Git worktrees:

1. Restore it to the indexed default-branch commit.
2. Create a uniquely named temporary non-default branch.
3. Generate, validate, review, and display the patch there.
4. On rejection or failure, discard changes, return to the indexed commit, and delete the local temporary branch.
5. On approval, commit and push the current non-default branch.
6. After a successful push, return the checkout to the indexed commit and remove the local generated branch.

The existing Git protection must reject pushes to the remote default branch. The pushed branch remains remote, but the vector index is unchanged because the default branch has not changed.

PR creation is outside scope because it requires provider-specific API integration.

## Streaming And Persistence

Questions and coding runs execute synchronously using server-sent events. Stream:

- Current stage.
- Generated answer or patch progress.
- Reviewer findings.
- Final citations, diff, and persisted result.

Do not add polling, WebSockets, or background agent execution. If the client disconnects during a coding run, cancel it, mark it failed, discard unapproved changes, and restore the checkout.

## Coding Run State

```text
queued
planning
retrieving
generating
reviewing
awaiting_approval
approved
rejected
failed
```

Only `awaiting_approval` may transition to `approved` or `rejected`. Exhausting Generation Retries escalates the best Patch Review to the owner rather than failing the run. Approval performs commit and push; failure during either operation transitions to `failed`.

Persist failures as:

```json
{
  "status": "failed",
  "failure_stage": "review | generation | validation | git_commit | git_push",
  "failure_reason": "sanitized human-readable message"
}
```

## Suggested FastAPI Surface

```text
POST /repositories
POST /repositories/{id}/sync
GET  /repositories/{id}

POST /sessions
POST /sessions/{id}/questions
POST /sessions/{id}/tasks

GET  /runs/{id}
GET  /runs/{id}/patch
POST /runs/{id}/approve
POST /runs/{id}/reject
```

Question and task creation endpoints return SSE streams. Approval and rejection are ordinary synchronous requests.
