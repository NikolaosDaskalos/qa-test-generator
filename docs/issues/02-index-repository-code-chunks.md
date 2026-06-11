# Index Repository files as commit-scoped Code Chunks

Status: ready-for-agent
Type: AFK
User stories: 5, 7-9, 69

## What to build

Complete initial Repository indexing so a successfully cloned Python Repository produces Repository Evidence tied to the exact default-branch commit. Use the existing Python-aware splitting strategy and user-scoped Weaviate tenancy, while making Repository identity and commit identity explicit on every Code Chunk.

Repositories without a usable Python codebase must fail or be reported as unsupported rather than becoming ready with misleading evidence.

## Acceptance criteria

- [ ] Initial processing resolves and records the default-branch commit represented by Repository Evidence.
- [ ] Only Python files from the checked-out default branch are loaded and split with the existing Python-aware recursive splitter.
- [ ] Every Code Chunk stores `repository_id`, `commit_sha`, `source`, and `parent_document_id`.
- [ ] Code Chunk identifiers are deterministic for the Repository snapshot and do not collide with chunks from another Repository.
- [ ] Weaviate writes remain isolated to the Repository owner's tenant.
- [ ] A Repository becomes ready only after all Code Chunks are written successfully and the indexed commit is persisted.
- [ ] A Repository with no usable Python files is reported as unsupported or failed with a sanitized reason.
- [ ] Ingestor, service, persistence, model, and migration tests cover metadata, commit persistence, tenant isolation, empty Python repositories, and failed vector writes.

## Blocked by

- [01 - Register and clone a GitHub Python Repository](01-register-clone-github-python-repository.md)

