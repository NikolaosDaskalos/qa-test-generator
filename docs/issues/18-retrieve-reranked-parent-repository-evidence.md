# Retrieve reranked parent Repository Evidence

Status: ready-for-agent
Type: AFK

## What to build

Upgrade repository-scoped retrieval so the candidate Code Chunks produced by
issue 04 select complete parent documents for generation. Rerank those
candidates with Cohere through the `langchain-cohere` integration.

Preserve the reranked order while deduplicating each chunk's `parent_id`, then
load up to the configured parent limit as `SourceDocument` records from
PostgreSQL. Standard and HyDE question flows must use these complete parent
documents as Repository Evidence instead of the candidate Code Chunks.

The final-parent limit must be configurable independently of issue 04's
candidate-chunk limit because several highly ranked chunks may belong to the
same parent document.

## Acceptance criteria

- [ ] The reranker receives only the repository-scoped candidate Code Chunks produced by issue 04.
- [ ] Remaining candidates are reranked against the retrieval query using Cohere through the `langchain-cohere` library.
- [ ] Reranked candidates without a valid `parent_id` are ignored, and duplicate parent IDs retain the order of their highest-ranked Code Chunk.
- [ ] Up to the configured number of unique parent `SourceDocument` records are fetched from PostgreSQL and returned in reranked order.
- [ ] A fetched `SourceDocument` is accepted only when it belongs to the requested Repository; missing or mismatched parent records are skipped without admitting cross-Repository evidence.
- [ ] Standard and HyDE answer generation format complete parent document content and metadata as Repository Evidence rather than chunk content.
- [ ] File citations remain traceable to the selected parent documents and do not expose discarded candidate chunks as answer sources.
- [ ] Empty hybrid results, empty reranker results, and missing parent records produce an empty Repository Evidence result without creating a tenant or fabricating context.
- [ ] Runtime configuration includes the Cohere API key, rerank model, and final-parent limit, and the backend declares the `langchain-cohere` dependency.
- [ ] Retriever, chain, and pipeline tests cover Cohere reranking, stable parent deduplication, ordered PostgreSQL hydration, Repository isolation, missing parents, both standard and HyDE flows, and dependency injection of the `SourceDocumentStore`.

## Blocked by

- [04 - Retrieve evidence only from the selected Repository](04-retrieve-repository-scoped-evidence.md)
