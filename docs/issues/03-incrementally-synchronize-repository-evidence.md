# Incrementally synchronize Repository Evidence

Status: ready-for-agent
Type: AFK
User stories: 10-17, 73

## What to build

Add a user-initiated Synchronization Request that fetches the latest default branch in the background and aligns Repository Evidence through file-level changes. Synchronization must handle added, modified, deleted, and renamed Python files without rebuilding unrelated Code Chunks.

The indexed commit must describe a fully applied snapshot: it advances only after every required vector operation succeeds.

## Acceptance criteria

- [ ] An authenticated owner can request synchronization for a ready Repository and receives an accepted response while work continues in a FastAPI background task.
- [ ] Synchronization fetches the latest default branch and compares it with the indexed commit using Git rename detection.
- [ ] Added Python files are indexed, modified files are replaced, deleted files are removed, and renamed files are removed under the old path and indexed under the new path.
- [ ] Non-Python file changes do not create Repository Evidence or trigger unrelated vector rewrites.
- [ ] A no-change synchronization completes successfully without rewriting existing Code Chunks.
- [ ] The indexed commit advances only after all file-level vector operations complete successfully.
- [ ] Fetch, diff, and vector failures preserve the previous indexed commit and expose a sanitized synchronization failure.
- [ ] Repository lookup exposes active, successful, and failed synchronization information.
- [ ] Tests cover add, modify, delete, rename, no-change, fetch failure, diff failure, vector failure, and atomic commit advancement.

## Blocked by

- [02 - Index Repository files as commit-scoped Code Chunks](02-index-repository-code-chunks.md)
- [30 - Concentrate Repository processing state behind named transitions](30-concentrate-repository-processing-state.md) — this work widens the same processing method, so the state moves should be concentrated first and this issue rebased onto the named transitions.

