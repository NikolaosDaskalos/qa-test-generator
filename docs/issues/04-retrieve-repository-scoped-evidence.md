# Retrieve evidence only from the selected Repository

Status: completed
Type: AFK
User stories: 26, 37, 69

## What to build

Retrieve candidate Code Chunks from Weaviate using hybrid BM25 and vector
search with reciprocal rank fusion (RRF). Retrieval must use the authenticated
user's tenant and require the selected Repository identity.

This slice provides the repository-scoped candidate set used by downstream
reranking and prevents Code Chunks from another Repository owned by the same
user from entering Repository Evidence.

## Acceptance criteria

- [x] The retrieval contract requires a Repository identity and cannot perform an unscoped evidence search.
- [x] Retrieval combines BM25 and vector search using Weaviate hybrid search with RRF.
- [x] Hybrid retrieval applies the authenticated user's tenant and a `repository_id` filter on every query.
- [x] The hybrid weighting and candidate count are configurable.
- [x] Retrieved documents retain source, Repository, commit, and parent metadata needed by downstream workflows.
- [x] Results belonging to another Repository in the same user tenant are excluded.
- [x] Missing tenants raise a retrieval error without creating new tenants; empty Repository results return no candidate Code Chunks.
- [x] Repository-level retrieval statistics, if exposed, are filtered to the selected Repository.
- [x] Retriever and RAG pipeline tests assert RRF hybrid options, the Repository query filter, and tenant isolation.

## Blocked by

- [02 - Index Repository files as commit-scoped Code Chunks](02-index-repository-code-chunks.md)
