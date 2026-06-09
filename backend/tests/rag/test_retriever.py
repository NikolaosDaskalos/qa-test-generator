"""Test tenant-aware hybrid retrieval and embedding lookups."""

from types import SimpleNamespace

from langchain_core.documents import Document

from app.core.config import settings
from app.core.weaviate_init import WeaviateResources
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
                objects=[
                    SimpleNamespace(
                        uuid="object-id", properties={"content": "body", "source": "file.py", "repository_id": "repo", "parent_document_id": "parent"}
                    )
                ]
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


def test_search_uses_configured_hybrid_options(monkeypatch) -> None:
    """Pass configured alpha, properties, limits, and tenant to search."""
    retriever, _, vector_store = _retriever()
    monkeypatch.setattr(settings, "HYBRID_SEARCH_ALPHA", 0.35)

    results = retriever.search_with_scores("exact_name", k=7)

    assert vector_store.call == ("exact_name", {"k": 7, "alpha": 0.35, "query_properties": ["content"], "tenant": "player-123"})
    assert results[0][1] == 0.9


def test_stats_existence_and_parent_lookup() -> None:
    """Return tenant statistics, existence checks, and parent chunks."""
    retriever, _, _ = _retriever()

    assert retriever.get_stats() == {"total_chunks": 2, "unique_sources": 2, "sources": ["a.py", "b.py"]}
    assert retriever.embedding_exists("existing") is True
    assert retriever.embedding_exists("missing") is False
    assert retriever.get_embeddings_by_parent_id("parent") == {
        "ids": ["object-id"],
        "documents": ["body"],
        "metadatas": [{"source": "file.py", "repository_id": "repo", "parent_document_id": "parent"}],
    }


def test_unknown_tenant_reads_are_empty_without_creation() -> None:
    """Return empty reads without creating an unknown tenant."""
    retriever, collection, vector_store = _retriever(tenant_exists=False)

    assert retriever.search_with_scores("query") == []
    assert retriever.get_stats() == {"total_chunks": 0, "unique_sources": 0, "sources": []}
    assert retriever.embedding_exists("existing") is False
    assert retriever.get_embeddings_by_parent_id("parent") == {"ids": [], "documents": [], "metadatas": []}
    assert collection.tenants.create_calls == []
    assert vector_store.call is None
