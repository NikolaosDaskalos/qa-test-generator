# Reorganize the Repository lifecycle

Status: completed
Type: AFK
User stories: 1-17, 80-84

## What to build

Reorganize Repository registration, credentials, processing, synchronization, listing, and deletion into a cohesive Repository feature module. Keep the HTTP routes thin, concentrate Repository policies and workflows in the feature, and place concrete database and Git behavior behind clear seams.

This is a structural refactor only. Existing endpoint contracts, ownership rules, background processing, status transitions, credential security, Repository Document indexing, synchronization, and failure sanitization must remain unchanged.

## Acceptance criteria

- [x] Repository schemas, workflows, policies, and background-task entry points have one predictable feature-oriented home.
- [x] Repository database records and persistence adapters have explicit placement under the shared database structure.
- [x] Concrete Git operations have explicit placement under integrations and do not leak transport concerns into Repository workflows.
- [x] FastAPI response codes and exceptions are translated at the HTTP seam rather than forming the Repository workflow interface.
- [x] Repository processing composes fresh database, Git, and RAG dependencies safely for background execution.
- [x] Registration, listing, credential update, deletion, initial indexing, synchronization, authorization, and sanitized failures behave exactly as before.
- [x] Existing API, workflow, persistence, Git, and integration tests pass through the reorganized imports.

## Blocked by

- [Issue 47](47-rename-rag-language-to-repository-documents.md)
