# Retrieve evidence only from the selected Repository

Status: ready-for-agent
Type: AFK
User stories: 26, 37, 69

## What to build

Retrieve candidate Code Chunks from Weaviate using hybrid BM25 and vector
search with reciprocal rank fusion (RRF). Retrieval must use the authenticated
user's tenant, require the selected Repository identity, and discard results
below the configured relevance threshold.

This slice provides the repository-scoped candidate set used by downstream
reranking and prevents Code Chunks from another Repository owned by the same
user from entering Repository Evidence.

## Acceptance criteria

- [ ] The retrieval contract requires a Repository identity and cannot perform an unscoped evidence search.
- [ ] Retrieval combines BM25 and vector search using Weaviate hybrid search with RRF.
- [ ] Hybrid retrieval applies the authenticated user's tenant and a `repository_id` filter on every query.
- [ ] The hybrid weighting, candidate count, and minimum relevance threshold are configurable.
- [ ] Results below the minimum relevance threshold are excluded from the candidate Code Chunks.
- [ ] Retrieved documents retain source, Repository, commit, and parent metadata needed by downstream workflows.
- [ ] Results belonging to another Repository in the same user tenant are excluded.
- [ ] Missing tenants, empty Repository results, and all-below-threshold results return no candidate Code Chunks without creating new tenants.
- [ ] Repository-level retrieval statistics, if exposed, are filtered to the selected Repository.
- [ ] Retriever and RAG pipeline tests assert RRF hybrid options, threshold filtering, the Repository query filter, and tenant isolation.

## Blocked by

- [02 - Index Repository files as commit-scoped Code Chunks](02-index-repository-code-chunks.md)
