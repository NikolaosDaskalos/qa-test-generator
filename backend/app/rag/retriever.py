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
        """Rerank candidate Code Chunks and hydrate their parent documents."""
        candidates = [document for document, _ in self.search_with_scores(query, repository_id=repository_id, k=k, alpha=alpha)]
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
