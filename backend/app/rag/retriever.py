"""Hybrid document retrieval and collection statistics."""

from typing import Any

from langchain_core.documents import Document
from weaviate.classes.query import Filter

from app.core.config import settings
from app.core.vector_db import METADATA_PROPERTIES, TEXT_PROPERTY, WeaviateResources


class DocumentRetriever:
    """Wrap Weaviate hybrid retrieval behind the RAG query contract."""

    def __init__(self, resources: WeaviateResources, tenant: str):
        """Initialize retrieval against a specific Weaviate tenant."""
        self.resources = resources
        self.tenant = tenant

    def search_with_scores(self, query: str, *, k: int | None = None) -> list[tuple[Document, float]]:
        """Combine BM25 keyword matching and vector similarity in Weaviate."""
        if not self._tenant_exists():
            return []
        return self.resources.vector_store.similarity_search_with_score(
            query, k=k or settings.TOP_K or 4, alpha=settings.HYBRID_SEARCH_ALPHA, query_properties=[TEXT_PROPERTY], tenant=self.tenant
        )

    def get_stats(self) -> dict[str, Any]:
        """Return chunk and source counts for the configured tenant."""
        if not self._tenant_exists():
            return {"total_chunks": 0, "unique_sources": 0, "sources": []}

        collection = self._collection().with_tenant(self.tenant)
        aggregate = collection.aggregate.over_all(total_count=True)
        sources = {obj.properties["source"] for obj in collection.iterator(include_vector=False, return_properties=["source"]) if obj.properties.get("source")}
        return {"total_chunks": aggregate.total_count or 0, "unique_sources": len(sources), "sources": sorted(sources)}

    def embedding_exists(self, embedding_id: str) -> bool:
        """Return whether an embedding object exists in the tenant."""
        if not embedding_id:
            return False
        if not self._tenant_exists():
            return False
        return self._collection().with_tenant(self.tenant).query.fetch_object_by_id(embedding_id) is not None

    def get_embeddings_by_parent_id(self, parent_id: str) -> dict[str, Any]:
        """Return chunks and metadata associated with a parent document.

        Raises:
            ValueError: If the parent document ID is empty.

        """
        if not parent_id:
            raise ValueError("parent_id cannot be empty")
        empty_result: dict[str, Any] = {"ids": [], "documents": [], "metadatas": []}
        if not self._tenant_exists():
            return empty_result

        response = (
            self._collection()
            .with_tenant(self.tenant)
            .query.fetch_objects(
                filters=Filter.by_property("parent_document_id").equal(parent_id), limit=10_000, return_properties=[TEXT_PROPERTY, *METADATA_PROPERTIES]
            )
        )
        return {
            "ids": [str(obj.uuid) for obj in response.objects],
            "documents": [obj.properties.get(TEXT_PROPERTY) for obj in response.objects],
            "metadatas": [{key: value for key, value in obj.properties.items() if key != TEXT_PROPERTY} for obj in response.objects],
        }

    def _tenant_exists(self) -> bool:
        """Return whether the configured tenant exists."""
        return self.tenant in self._collection().tenants.get_by_names([self.tenant])

    def _collection(self) -> Any:
        """Return the configured Weaviate collection."""
        return self.resources.client.collections.get(settings.WEAVIATE_COLLECTION)
