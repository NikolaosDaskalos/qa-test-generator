"""Test tenant-aware document ingestion and deletion behavior."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.core.config import settings
from app.core.vector_db import WeaviateResources
from app.errors.rag_errors import IngestorError
from app.rag.ingestor import DocumentIngestor


class FakeTenants:
    """Maintain an in-memory set of Weaviate tenant names."""

    def __init__(self) -> None:
        """Initialize an empty tenant registry."""
        self.names: set[str] = set()

    def get_by_names(self, names):
        """Return known tenants matching the requested names."""
        return {name: object() for name in names if name in self.names}

    def create(self, tenants):
        """Add tenant objects to the registry."""
        self.names.update(tenant.name for tenant in tenants)


class FakeTenantCollection:
    """Record tenant-scoped deletion filters."""

    def __init__(self) -> None:
        """Initialize deletion tracking."""
        self.deleted_filters = []
        self.data = SimpleNamespace(delete_many=self.delete_many)

    def delete_many(self, *, where):
        """Record a bulk-deletion filter."""
        self.deleted_filters.append(where)


class FakeCollection:
    """Provide tenant management and tenant-scoped collections."""

    def __init__(self) -> None:
        """Initialize tenant registries and collection storage."""
        self.tenants = FakeTenants()
        self.tenant_collections = {}

    def with_tenant(self, tenant):
        """Return or create a fake collection for a tenant."""
        return self.tenant_collections.setdefault(tenant, FakeTenantCollection())


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
    """Provide a minimal Weaviate client for ingestion tests."""

    def __init__(self, collection) -> None:
        """Initialize the client with one fake collection."""
        self.collections = FakeCollections(collection)


class FakeVectorStore:
    """Record vector-store additions and deletions."""

    def __init__(self) -> None:
        """Initialize call tracking."""
        self.add_calls = []
        self.delete_calls = []

    def add_documents(self, documents, **kwargs):
        """Record documents and return their supplied IDs."""
        self.add_calls.append((documents, kwargs))
        return kwargs["ids"]

    def delete(self, **kwargs):
        """Record a vector-store deletion call."""
        self.delete_calls.append(kwargs)


class FakeSourceDocumentStore:
    """Record source-document replacement and cleanup."""

    def __init__(self) -> None:
        self.replace_calls = []
        self.delete_calls = []

    def replace_for_repository(self, repository_id, source_documents):
        self.replace_calls.append((repository_id, source_documents))
        return source_documents

    def delete_by_repository(self, repository_id):
        self.delete_calls.append(repository_id)


def _resources() -> WeaviateResources:
    """Build shared resources from ingestion test doubles."""
    return WeaviateResources(client=FakeClient(FakeCollection()), vector_store=FakeVectorStore())


def _bare_ingestor(documents, resources):
    """Build an ingestor without loading the real tokenizer."""
    ingestor = DocumentIngestor(resources, FakeSourceDocumentStore())
    ingestor._load = lambda *args: documents
    ingestor._split = lambda *args: documents
    return ingestor


def test_ingestion_replaces_repository_chunks_with_deterministic_ids() -> None:
    """Replace existing chunks while preserving deterministic IDs."""
    repository_id = uuid.uuid4()
    user_id = uuid.uuid4()
    commit_sha = "a" * 40
    resources = _resources()
    documents = [Document(page_content="print('one')", metadata={"source": "one.py"}), Document(page_content="print('two')", metadata={"source": "two.py"})]
    ingestor = _bare_ingestor(documents, resources)

    first_count = ingestor.ingest(Path("/repo"), repository_id, "main", commit_sha, user_id)
    first_ids = resources.vector_store.add_calls[0][1]["ids"]
    second_count = ingestor.ingest(Path("/repo"), repository_id, "main", commit_sha, user_id)

    assert first_count == second_count == 2
    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    assert collection.tenants.names == {str(user_id)}
    assert resources.vector_store.add_calls[1][1]["ids"] == first_ids
    assert resources.vector_store.add_calls[0][1]["tenant"] == str(user_id)
    assert len(collection.with_tenant(str(user_id)).deleted_filters) == 2


def test_ingestion_stores_repository_snapshot_metadata_and_ids() -> None:
    """Identify every Code Chunk by Repository, commit SHA, and source path."""
    repository_id = uuid.uuid4()
    user_id = uuid.uuid4()
    resources = _resources()
    documents = [Document(page_content="print('one')", metadata={"source": "one.py"})]
    ingestor = _bare_ingestor(documents, resources)

    ingestor.ingest(Path("/repo"), repository_id, "main", "a" * 40, user_id)
    first_documents, first_options = resources.vector_store.add_calls[0]
    first_metadata = dict(first_documents[0].metadata)
    ingestor.ingest(Path("/repo"), repository_id, "main", "b" * 40, user_id)
    second_documents, second_options = resources.vector_store.add_calls[1]
    second_metadata = dict(second_documents[0].metadata)
    ingestor.ingest(Path("/repo"), uuid.uuid4(), "main", "a" * 40, user_id)
    third_options = resources.vector_store.add_calls[2][1]

    assert first_metadata == {
        "source": "one.py",
        "repository_id": str(repository_id),
        "commit_sha": "a" * 40,
        "parent_id": str(uuid.uuid5(repository_id, f"{'a' * 40}:one.py")),
    }
    assert second_metadata["commit_sha"] == "b" * 40
    assert first_options["ids"] != second_options["ids"]
    assert first_options["ids"] != third_options["ids"]


def test_empty_ingestion_is_rejected_without_writes() -> None:
    """Reject repositories that contain no usable Python documents."""
    resources = _resources()
    ingestor = _bare_ingestor([], resources)

    with pytest.raises(IngestorError, match="no Python files"):
        ingestor.ingest(Path("/repo"), uuid.uuid4(), "main", "a" * 40, uuid.uuid4())

    assert resources.vector_store.add_calls == []
    assert ingestor.source_document_store.replace_calls == []


def test_repository_deletion_is_idempotent_when_tenant_is_missing() -> None:
    """Do not create a tenant solely to delete absent repository chunks."""
    resources = _resources()
    ingestor = DocumentIngestor(resources, FakeSourceDocumentStore())
    user_id = uuid.uuid4()

    ingestor.delete_repository(uuid.uuid4(), user_id=user_id)

    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    assert collection.tenants.names == set()
    assert collection.tenant_collections == {}


def test_repository_deletion_uses_existing_user_tenant() -> None:
    """Delete repository chunks only within the owner's existing tenant."""
    resources = _resources()
    ingestor = DocumentIngestor(resources, FakeSourceDocumentStore())
    user_id = uuid.uuid4()
    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    collection.tenants.names.add(str(user_id))

    ingestor.delete_repository(uuid.uuid4(), user_id=user_id)

    assert len(collection.with_tenant(str(user_id)).deleted_filters) == 1


def test_ingestion_uses_shared_resources_when_write_fails() -> None:
    """Keep the shared resource instance when a write propagates failure."""
    resources = _resources()
    ingestor = _bare_ingestor([Document(page_content="content", metadata={"source": "file.py"})], resources)
    resources.vector_store.add_documents = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("write failed"))

    with pytest.raises(RuntimeError, match="write failed"):
        repository_id = uuid.uuid4()
        ingestor.ingest(Path("/repo"), repository_id, "main", "a" * 40, uuid.uuid4())

    assert ingestor.resources is resources
    assert ingestor.source_document_store.delete_calls == [repository_id]


def test_preserved_deletion_methods_use_shared_resources() -> None:
    """Route ID- and parent-based deletions through shared resources."""
    resources = _resources()
    ingestor = DocumentIngestor(resources, FakeSourceDocumentStore())
    user_id = uuid.uuid4()

    ingestor.delete_embeddings(["one", "two"], user_id=user_id)
    ingestor.delete_embeddings_by_parent_id("parent", user_id=user_id)

    assert resources.vector_store.delete_calls == [{"ids": ["one", "two"], "tenant": str(user_id)}]
    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    assert len(collection.with_tenant(str(user_id)).deleted_filters) == 1


def test_add_documents_validates_ids_and_uses_shared_resources() -> None:
    """Validate explicit IDs before adding tenant-scoped documents."""
    resources = _resources()
    ingestor = DocumentIngestor(resources, FakeSourceDocumentStore())
    user_id = uuid.uuid4()
    documents = [Document(page_content="content")]

    ids = ingestor.add_documents(documents, ids=["id"], user_id=user_id)

    assert ids == ["id"]
    assert resources.vector_store.add_calls[0][1] == {"ids": ["id"], "tenant": str(user_id)}

    with pytest.raises(ValueError, match="ids length"):
        ingestor.add_documents(documents, ids=[], user_id=user_id)
