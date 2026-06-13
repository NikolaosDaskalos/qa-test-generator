"""Test tenant-aware hybrid retrieval and collection statistics."""

import uuid
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from weaviate.classes.query import HybridFusion

from app.core.config import settings
from app.core.vector_db import WeaviateResources
from app.errors.rag_errors import RetrieverError
from app.models.source_document import SourceDocument
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
        self.aggregate = FakeAggregate()
        self.query = SimpleNamespace(
            fetch_object_by_id=lambda object_id: (object() if object_id == "existing" else None),
            fetch_objects=lambda **kwargs: SimpleNamespace(
                objects=[SimpleNamespace(uuid="object-id", properties={"content": "body", "source": "file.py", "repository_id": "repo", "parent_id": "parent"})]
            ),
        )


class FakeAggregate:
    """Record Repository filters used for aggregate statistics."""

    def __init__(self) -> None:
        self.calls = []

    def over_all(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("group_by"):
            return SimpleNamespace(
                groups=[SimpleNamespace(grouped_by=SimpleNamespace(value="b.py")), SimpleNamespace(grouped_by=SimpleNamespace(value="a.py"))]
            )
        return SimpleNamespace(total_count=2)


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

    def __init__(self, results=None) -> None:
        """Initialize search-call tracking."""
        self.call = None
        self.results = [(Document(page_content="result"), 0.9)] if results is None else results

    def similarity_search_with_score(self, query, **kwargs):
        """Record a scored similarity search."""
        self.call = (query, kwargs)
        return self.results


class FakeReranker:
    """Return candidate Code Chunks in a deterministic reranked order."""

    def __init__(self, results=None) -> None:
        self.call = None
        self.results = results

    def compress_documents(self, documents, query):
        self.call = (documents, query)
        return list(reversed(documents)) if self.results is None else self.results


class FakeSourceDocumentStore:
    """Load persisted parent SourceDocuments by identity."""

    def __init__(self, documents=()) -> None:
        self.documents = {document.id: document for document in documents}

    def get_by_id(self, source_document_id):
        return self.documents.get(source_document_id)


def _retriever(*, tenant_exists=True, results=None, source_documents=(), reranked_documents=None):
    """Build a retriever and its underlying test doubles."""
    tenant = "player-123"
    collection = FakeCollection([tenant] if tenant_exists else [])
    vector_store = FakeVectorStore(results)
    resources = WeaviateResources(FakeClient(collection), vector_store)
    reranker = FakeReranker(reranked_documents)
    source_document_store = FakeSourceDocumentStore(source_documents)
    return DocumentRetriever(resources, tenant, source_document_store, reranker), collection, vector_store, reranker


def test_search_uses_repository_scoped_hybrid_options() -> None:
    """Pass repository scope, alpha, properties, limits, and tenant to search."""
    retriever, _, vector_store, _ = _retriever()
    repository_id = uuid.uuid4()

    results = retriever.search_with_scores("exact_name", repository_id=repository_id, k=7, alpha=0.35)

    query, options = vector_store.call
    repository_filter = options.pop("filters")
    assert query == "exact_name"
    assert options == {"k": 7, "alpha": 0.35, "fusion_type": HybridFusion.RANKED, "query_properties": ["content"], "tenant": "player-123"}
    assert repository_filter.target == "repository_id"
    assert repository_filter.value == str(repository_id)
    assert results[0][1] == 0.9


def test_search_returns_all_ranked_code_chunks() -> None:
    """Return every Repository-scoped Code Chunk selected by hybrid search."""
    first = Document(page_content="first")
    second = Document(page_content="second")
    retriever, _, _, _ = _retriever(results=[(first, 0.02), (second, 0.01)])

    results = retriever.search_with_scores("query", repository_id=uuid.uuid4(), k=5, alpha=0.6)

    assert results == [(first, 0.02), (second, 0.01)]


def test_search_returns_no_candidates_when_repository_has_no_results() -> None:
    """Return no candidate Code Chunks when hybrid search finds no results."""
    retriever, _, _, _ = _retriever(results=[])

    results = retriever.search_with_scores("query", repository_id=uuid.uuid4(), k=5, alpha=0.6)

    assert results == []


def test_search_retains_repository_evidence_metadata() -> None:
    """Keep source, Repository, commit, and parent identity on candidate Code Chunks."""
    repository_id = uuid.uuid4()
    document = Document(
        page_content="def test_subject(): ...",
        metadata={"source": "tests/test_subject.py", "repository_id": str(repository_id), "commit_sha": "a" * 40, "parent_id": str(uuid.uuid4())},
    )
    retriever, _, _, _ = _retriever(results=[(document, 0.8)])

    results = retriever.search_with_scores("test subject", repository_id=repository_id, k=5, alpha=0.6)

    assert results == [(document, 0.8)]


def test_retrieve_evidence_reranks_candidates_and_hydrates_the_top_parent() -> None:
    """Return the complete parent selected by Cohere from candidate Code Chunks."""
    repository_id = uuid.uuid4()
    first_parent = SourceDocument(repository_id=repository_id, content="complete first file", doc_metadata={"source": "first.py"})
    second_parent = SourceDocument(repository_id=repository_id, content="complete second file", doc_metadata={"source": "second.py"})
    first_chunk = Document(page_content="first chunk", metadata={"parent_id": str(first_parent.id)})
    second_chunk = Document(page_content="second chunk", metadata={"parent_id": str(second_parent.id)})
    retriever, _, _, reranker = _retriever(
        results=[(first_chunk, 0.9), (second_chunk, 0.8)], source_documents=[first_parent, second_parent]
    )

    evidence = retriever.retrieve_evidence("find behavior", repository_id=repository_id, k=10, alpha=0.5, parent_limit=1)

    assert evidence == [second_parent]
    assert reranker.call == ([first_chunk, second_chunk], "find behavior")


def test_retrieve_evidence_ignores_invalid_parent_ids_and_stably_deduplicates() -> None:
    """Keep each valid parent once at its highest-ranked Code Chunk position."""
    repository_id = uuid.uuid4()
    first_parent = SourceDocument(repository_id=repository_id, content="complete first file", doc_metadata={"source": "first.py"})
    second_parent = SourceDocument(repository_id=repository_id, content="complete second file", doc_metadata={"source": "second.py"})
    lower_ranked_duplicate = Document(page_content="duplicate first chunk", metadata={"parent_id": str(first_parent.id)})
    invalid_parent = Document(page_content="orphan chunk", metadata={"parent_id": "not-a-uuid"})
    first_parent_chunk = Document(page_content="best first chunk", metadata={"parent_id": str(first_parent.id)})
    second_parent_chunk = Document(page_content="best second chunk", metadata={"parent_id": str(second_parent.id)})
    retriever, _, _, _ = _retriever(
        results=[
            (lower_ranked_duplicate, 0.6),
            (invalid_parent, 0.7),
            (first_parent_chunk, 0.8),
            (second_parent_chunk, 0.9),
        ],
        source_documents=[first_parent, second_parent],
    )

    evidence = retriever.retrieve_evidence("find behavior", repository_id=repository_id, k=10, alpha=0.5, parent_limit=3)

    assert evidence == [second_parent, first_parent]


def test_retrieve_evidence_skips_missing_and_cross_repository_parents() -> None:
    """Return only hydrated parents that belong to the requested Repository."""
    repository_id = uuid.uuid4()
    valid_parent = SourceDocument(repository_id=repository_id, content="valid parent", doc_metadata={"source": "valid.py"})
    mismatched_parent = SourceDocument(repository_id=uuid.uuid4(), content="other Repository", doc_metadata={"source": "other.py"})
    missing_parent_id = uuid.uuid4()
    valid_chunk = Document(page_content="valid chunk", metadata={"parent_id": str(valid_parent.id)})
    missing_chunk = Document(page_content="missing chunk", metadata={"parent_id": str(missing_parent_id)})
    mismatched_chunk = Document(page_content="mismatched chunk", metadata={"parent_id": str(mismatched_parent.id)})
    retriever, _, _, _ = _retriever(
        results=[(valid_chunk, 0.7), (missing_chunk, 0.8), (mismatched_chunk, 0.9)],
        source_documents=[valid_parent, mismatched_parent],
    )

    evidence = retriever.retrieve_evidence("find behavior", repository_id=repository_id, k=10, alpha=0.5, parent_limit=2)

    assert evidence == [valid_parent]


def test_retrieve_evidence_returns_empty_when_candidates_or_reranking_are_empty() -> None:
    """Produce no Repository Evidence when either retrieval stage has no results."""
    repository_id = uuid.uuid4()
    no_candidates_retriever, _, _, unused_reranker = _retriever(results=[])

    assert no_candidates_retriever.retrieve_evidence(
        "find behavior", repository_id=repository_id, k=10, alpha=0.5, parent_limit=2
    ) == []
    assert unused_reranker.call is None

    candidate = Document(page_content="candidate", metadata={"parent_id": str(uuid.uuid4())})
    no_reranks_retriever, _, _, used_reranker = _retriever(results=[(candidate, 0.9)], reranked_documents=[])

    assert no_reranks_retriever.retrieve_evidence(
        "find behavior", repository_id=repository_id, k=10, alpha=0.5, parent_limit=2
    ) == []
    assert used_reranker.call == ([candidate], "find behavior")


def test_stats_returns_repository_chunk_and_source_counts() -> None:
    """Return statistics filtered to the selected Repository."""
    retriever, collection, _, _ = _retriever()
    repository_id = uuid.uuid4()

    assert retriever.get_stats(repository_id=repository_id) == {"total_chunks": 2, "unique_sources": 2, "sources": ["a.py", "b.py"]}
    count_options, source_options = collection.tenant_collection.aggregate.calls
    for options in (count_options, source_options):
        repository_filter = options["filters"]
        assert repository_filter.target == "repository_id"
        assert repository_filter.value == str(repository_id)
    assert source_options["group_by"].prop == "source"


def test_unknown_tenant_operations_raise_without_creation() -> None:
    """Reject retrieval operations without creating an unknown tenant."""
    retriever, collection, vector_store, _ = _retriever(tenant_exists=False)
    repository_id = uuid.uuid4()

    with pytest.raises(RetrieverError, match="tenant does not exist"):
        retriever.search_with_scores("query", repository_id=repository_id, k=3, alpha=0.7)

    with pytest.raises(RetrieverError, match="tenant does not exist"):
        retriever.get_stats(repository_id=repository_id)

    assert collection.tenants.create_calls == []
    assert vector_store.call is None
