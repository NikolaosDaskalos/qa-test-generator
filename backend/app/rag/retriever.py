"""Hybrid document retrieval and collection statistics."""

import logging
import uuid
from typing import Any

from langchain_cohere import CohereRerank
from langchain_core.documents import Document
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter, HybridFusion

from app.core import settings
from app.core.errors.rag_errors import RetrieverError
from app.db.models import RepositoryDocument
from app.db.persistence import RepositoryDocumentStore
from app.integrations.weaviate import TEXT_PROPERTY, WeaviateResources

logger = logging.getLogger(__name__)


def _chunk_identity(document: Document) -> tuple:
    """A stable per-chunk identity for fusion: parent document plus chunk text.

    Keying on text alone would collapse identical-text chunks from *different* parents
    into one fused candidate, making a dropped parent unreachable (only the fused pool is
    later reranked and hydrated). Pairing the parent id with the text keeps distinct
    parents distinct, while still treating the same chunk found by several query variants
    as one. Sibling chunks of a single parent that happen to share text collapse harmlessly,
    since hydration de-duplicates by parent anyway.
    """
    return (document.metadata.get("parent_id"), document.page_content)


def reciprocal_rank_fusion(ranked_lists: list[list[Document]], *, k: int) -> list[Document]:
    """Merge several ranked Code Chunk lists into one by Reciprocal Rank Fusion.

    Each chunk scores ``sum(1 / (k + rank))`` over every list it appears in (rank
    1-based), so a chunk surfacing under several query reformulations outranks one
    found by a single variant — this is the cross-reformulation recall signal. Chunks
    are identified by ``(parent_id, text)`` (see ``_chunk_identity``); the first-seen
    instance is kept. Returns chunks in descending fused score, ties broken by first
    appearance (stable).
    """
    scores: dict[tuple, float] = {}
    first_seen: dict[tuple, Document] = {}
    order: list[tuple] = []
    for ranked in ranked_lists:
        for rank, document in enumerate(ranked, start=1):
            identity = _chunk_identity(document)
            if identity not in first_seen:
                first_seen[identity] = document
                order.append(identity)
                scores[identity] = 0.0
            scores[identity] += 1.0 / (k + rank)
    order.sort(key=lambda identity: scores[identity], reverse=True)
    return [first_seen[identity] for identity in order]


class DocumentRetriever:
    """Wrap Weaviate hybrid retrieval behind the RAG query contract."""

    def __init__(self, resources: WeaviateResources, tenant: str, repository_document_store: RepositoryDocumentStore, reranker: CohereRerank):
        """Initialize retrieval against a specific Weaviate tenant."""
        self.resources = resources
        self.tenant = tenant
        self.repository_document_store = repository_document_store
        self.reranker = reranker

    def search_with_scores(self, query: str, *, repository_id: uuid.UUID, k: int, alpha: float) -> list[tuple[Document, float]]:
        """Combine BM25 keyword matching and vector similarity in Weaviate."""
        if not self._tenant_exists():
            logger.warning("Document search skipped because tenant does not exist tenant=%s", self.tenant)
            raise RetrieverError("Document search skipped because tenant does not exist")
        results = self.resources.vector_store.similarity_search_with_score(
            query=query,
            k=k,
            alpha=alpha,
            fusion_type=HybridFusion.RANKED,
            query_properties=[TEXT_PROPERTY],
            filters=Filter.by_property("repository_id").equal(str(repository_id)),
            tenant=self.tenant,
        )
        logger.info("Document search completed tenant=%s result_count=%s", self.tenant, len(results))
        return results

    def retrieve_documents(self, query: str, *, repository_id: uuid.UUID, k: int, alpha: float, parent_limit: int) -> list[RepositoryDocument]:
        """Rerank candidate Code Chunks from a single query and hydrate their parent documents."""
        candidates = [document for document, _ in self.search_with_scores(query, repository_id=repository_id, k=k, alpha=alpha)]
        return self._rerank_and_hydrate(candidates, query, repository_id=repository_id, parent_limit=parent_limit)

    def fusion_retrieve_documents(
        self, queries: list[str], *, original_query: str, repository_id: uuid.UUID, k: int, alpha: float, parent_limit: int, rrf_k: int
    ) -> list[RepositoryDocument]:
        """Multi-query + RAG-fusion: raw hybrid search per variant, RRF-fuse, then rerank against the original.

        Each query variant runs the same raw hybrid search as the single-query path; the
        ranked Code Chunk lists are merged by Reciprocal Rank Fusion (widening recall across
        reformulations) and the fused pool is handed to the same rerank/hydrate tail —
        scored once by the Cohere cross-encoder against the original question for precision.
        """
        ranked_lists = [
            [document for document, _ in self.search_with_scores(query, repository_id=repository_id, k=k, alpha=alpha)] for query in queries
        ]
        fused = reciprocal_rank_fusion(ranked_lists, k=rrf_k)
        return self._rerank_and_hydrate(fused, original_query, repository_id=repository_id, parent_limit=parent_limit)

    def _rerank_and_hydrate(self, candidates: list[Document], query: str, *, repository_id: uuid.UUID, parent_limit: int) -> list[RepositoryDocument]:
        """Rerank candidate Code Chunks against ``query`` and hydrate their parent documents."""
        if not candidates:
            return []

        reranked_candidates = self.reranker.compress_documents(candidates, query)
        documents: list[RepositoryDocument] = []
        seen_parent_ids = set()
        for candidate in reranked_candidates:
            try:
                parent_id = uuid.UUID(candidate.metadata.get("parent_id", ""))
            except (AttributeError, TypeError, ValueError):
                continue
            if parent_id in seen_parent_ids:
                continue
            seen_parent_ids.add(parent_id)
            parent = self.repository_document_store.get_by_id(parent_id)
            if parent is not None and parent.repository_id == repository_id:
                documents.append(parent)
            if len(documents) == parent_limit:
                break
        return documents

    def get_stats(self, *, repository_id: uuid.UUID) -> dict[str, Any]:
        """Return chunk and source counts for one Repository."""
        if not self._tenant_exists():
            logger.warning("Document statistics requested for missing tenant=%s", self.tenant)
            raise RetrieverError("Document statistics skipped because tenant does not exist")

        collection = self._collection().with_tenant(self.tenant)
        repository_filter = Filter.by_property("repository_id").equal(str(repository_id))
        chunk_aggregate = collection.aggregate.over_all(total_count=True, filters=repository_filter)
        source_aggregate = collection.aggregate.over_all(filters=repository_filter, group_by=GroupByAggregate(prop="source"))
        sources = sorted(group.grouped_by.value for group in source_aggregate.groups if group.grouped_by.value)
        logger.info(
            "Document statistics loaded tenant=%s repository_id=%s chunk_count=%s source_count=%s",
            self.tenant,
            repository_id,
            chunk_aggregate.total_count or 0,
            len(sources),
        )
        return {"total_chunks": chunk_aggregate.total_count or 0, "unique_sources": len(sources), "sources": sources}

    def _tenant_exists(self) -> bool:
        """Return whether the configured tenant exists."""
        return self.tenant in self._collection().tenants.get_by_names([self.tenant])

    def _collection(self) -> Any:
        """Return the configured Weaviate collection."""
        return self.resources.client.collections.get(settings.WEAVIATE_COLLECTION)
