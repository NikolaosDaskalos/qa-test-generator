"""Hybrid document retrieval and collection statistics."""

import logging
import uuid
from typing import Any

from langchain_core.documents import Document
from weaviate.classes.query import Filter

from app.core.config import settings
from app.core.vector_db import TEXT_PROPERTY, WeaviateResources
from app.errors.rag_errors import RetrieverError

logger = logging.getLogger(__name__)


class DocumentRetriever:
    """Wrap Weaviate hybrid retrieval behind the RAG query contract."""

    def __init__(self, resources: WeaviateResources, tenant: str):
        """Initialize retrieval against a specific Weaviate tenant."""
        self.resources = resources
        self.tenant = tenant

    def search_with_scores(self, query: str, *, repository_id: uuid.UUID, k: int = 4, alpha: float) -> list[tuple[Document, float]]:
        """Combine BM25 keyword matching and vector similarity in Weaviate."""
        if not self._tenant_exists():
            logger.warning("Document search skipped because tenant does not exist tenant=%s", self.tenant)
            raise RetrieverError("Document search skipped because tenant does not exist")
        results = self.resources.vector_store.similarity_search_with_score(
            query=query,
            k=k,
            alpha=alpha,
            query_properties=[TEXT_PROPERTY],
            filters=Filter.by_property("repository_id").equal(str(repository_id)),
            tenant=self.tenant,
        )
        logger.info("Document search completed tenant=%s result_count=%s", self.tenant, len(results))
        return results

    def get_stats(self) -> dict[str, Any]:
        """Return chunk and source counts for the configured tenant."""
        if not self._tenant_exists():
            logger.warning("Document statistics requested for missing tenant=%s", self.tenant)
            return {"total_chunks": 0, "unique_sources": 0, "sources": []}

        collection = self._collection().with_tenant(self.tenant)
        aggregate = collection.aggregate.over_all(total_count=True)
        sources = {obj.properties["source"] for obj in collection.iterator(include_vector=False, return_properties=["source"]) if obj.properties.get("source")}
        logger.info("Document statistics loaded tenant=%s chunk_count=%s source_count=%s", self.tenant, aggregate.total_count or 0, len(sources))
        return {"total_chunks": aggregate.total_count or 0, "unique_sources": len(sources), "sources": sorted(sources)}

    def _tenant_exists(self) -> bool:
        """Return whether the configured tenant exists."""
        return self.tenant in self._collection().tenants.get_by_names([self.tenant])

    def _collection(self) -> Any:
        """Return the configured Weaviate collection."""
        return self.resources.client.collections.get(settings.WEAVIATE_COLLECTION)
