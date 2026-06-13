"""Test tenant-aware hybrid retrieval and collection statistics."""

import uuid
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.core.config import settings
from app.core.vector_db import WeaviateResources
from app.errors.rag_errors import RetrieverError
from app.rag.retriever import DocumentRetriever


class FakeTenants:
    """Represent the tenant names available to the retriever."""

    def __init__(self, names=()) -> None:
        """Initialize known tenant names and creation tracking."""
        self.names = set(names)
        self.create_calls = []

    def get_by_names(self, names):
        """Return known tenants matching the requested names."""
        return {name: object() for name in names if name in self.names}

    def create(self, tenants):
        """Record unexpected tenant creation calls."""
        self.create_calls.append(tenants)


class FakeTenantCollection:
    """Provide aggregate, query, and iteration results for one tenant."""

    def __init__(self) -> None:
        """Initialize deterministic collection responses."""
        self.aggregate = SimpleNamespace(over_all=lambda **kwargs: SimpleNamespace(total_count=2))
        self.query = SimpleNamespace(
            fetch_object_by_id=lambda object_id: (object() if object_id == "existing" else None),
            fetch_objects=lambda **kwargs: SimpleNamespace(
                objects=[SimpleNamespace(uuid="object-id", properties={"content": "body", "source": "file.py", "repository_id": "repo", "parent_id": "parent"})]
            ),
        )

    def iterator(self, **kwargs):
        """Return source records containing one duplicate source."""
        return [SimpleNamespace(properties={"source": "b.py"}), SimpleNamespace(properties={"source": "a.py"}), SimpleNamespace(properties={"source": "a.py"})]


class FakeCollection:
    """Provide tenant lookup and tenant-scoped collection access."""

    def __init__(self, tenants=()) -> None:
        """Initialize the collection with known tenants."""
        self.tenants = FakeTenants(tenants)
        self.tenant_collection = FakeTenantCollection()

    def with_tenant(self, tenant):
        """Return the fake tenant collection."""
        return self.tenant_collection


class FakeCollections:
    """Expose one collection through the client registry API."""

    def __init__(self, collection) -> None:
        """Store the collection returned by lookups."""
        self.collection = collection

    def get(self, name):
        """Return the configured collection after checking its name."""
        assert name == settings.WEAVIATE_COLLECTION
        return self.collection


class FakeClient:
    """Provide a minimal Weaviate client for retrieval tests."""

    def __init__(self, collection) -> None:
        """Initialize the client with one fake collection."""
        self.collections = FakeCollections(collection)


class FakeVectorStore:
    """Record hybrid search arguments and return a scored document."""

    def __init__(self) -> None:
        """Initialize search-call tracking."""
        self.call = None

    def similarity_search_with_score(self, query, **kwargs):
        """Record a scored similarity search."""
        self.call = (query, kwargs)
        return [(Document(page_content="result"), 0.9)]


def _retriever(*, tenant_exists=True):
    """Build a retriever and its underlying test doubles."""
    tenant = "player-123"
    collection = FakeCollection([tenant] if tenant_exists else [])
    vector_store = FakeVectorStore()
    resources = WeaviateResources(FakeClient(collection), vector_store)
    return DocumentRetriever(resources, tenant), collection, vector_store


def test_search_uses_repository_scoped_hybrid_options() -> None:
    """Pass repository scope, alpha, properties, limits, and tenant to search."""
    retriever, _, vector_store = _retriever()
    repository_id = uuid.uuid4()

    results = retriever.search_with_scores("exact_name", repository_id=repository_id, k=7, alpha=0.35)

    query, options = vector_store.call
    repository_filter = options.pop("filters")
    assert query == "exact_name"
    assert options == {"k": 7, "alpha": 0.35, "query_properties": ["content"], "tenant": "player-123"}
    assert repository_filter.target == "repository_id"
    assert repository_filter.value == str(repository_id)
    assert results[0][1] == 0.9


def test_stats_returns_tenant_chunk_and_source_counts() -> None:
    """Return tenant statistics with sorted unique source names."""
    retriever, _, _ = _retriever()

    assert retriever.get_stats() == {"total_chunks": 2, "unique_sources": 2, "sources": ["a.py", "b.py"]}


def test_unknown_tenant_search_raises_without_creation() -> None:
    """Reject search without creating an unknown tenant."""
    retriever, collection, vector_store = _retriever(tenant_exists=False)
    repository_id = uuid.uuid4()

    with pytest.raises(RetrieverError, match="tenant does not exist"):
        retriever.search_with_scores("query", repository_id=repository_id, alpha=0.7)

    assert retriever.get_stats() == {"total_chunks": 0, "unique_sources": 0, "sources": []}
    assert collection.tenants.create_calls == []
    assert vector_store.call is None
