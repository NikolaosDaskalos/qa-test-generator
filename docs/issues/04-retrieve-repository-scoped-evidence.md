# Retrieve evidence only from the selected Repository

Status: ready-for-agent
Type: AFK
User stories: 26, 37, 69

## What to build

Make hybrid retrieval explicitly Repository-scoped. Retrieval must continue to use the authenticated user's Weaviate tenant, but every evidence query must additionally require the Repository identity selected by the caller.

This slice prevents chunks from another Repository owned by the same user from entering answers, plans, generated tests, or Patch Review.

## Acceptance criteria

- [ ] The retrieval contract requires a Repository identity and cannot perform an unscoped evidence search.
- [ ] Hybrid retrieval applies both the user tenant and a `repository_id` filter on every query.
- [ ] Retrieved documents retain source, Repository, commit, and parent metadata needed by downstream workflows.
- [ ] Results belonging to another Repository in the same user tenant are excluded.
- [ ] Missing tenants and empty Repository result sets return no Repository Evidence without creating new tenants.
- [ ] Repository-level retrieval statistics, if exposed, are filtered to the selected Repository.
- [ ] Retriever and RAG pipeline tests assert the query filter and prove that cross-Repository chunks cannot enter Repository Evidence.

## Blocked by

- [02 - Index Repository files as commit-scoped Code Chunks](02-index-repository-code-chunks.md)

