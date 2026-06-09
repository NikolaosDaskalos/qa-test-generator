"""Test shared Weaviate initialization and schema validation."""

from types import SimpleNamespace

import pytest
from weaviate.classes.config import DataType, Vectorizers

from app.core import weaviate_init
from app.core.config import settings


class FakeCollection:
    """Represent a collection with configurable schema properties."""

    def __init__(self, *, multi_tenancy: bool = True, properties: dict[str, DataType] | None = None, vectorizer: Vectorizers = Vectorizers.NONE) -> None:
        """Create a fake collection configuration."""
        property_types = properties or {weaviate_init.TEXT_PROPERTY: DataType.TEXT, **dict.fromkeys(weaviate_init.METADATA_PROPERTIES, DataType.TEXT)}
        self.config = SimpleNamespace(
            get=lambda: SimpleNamespace(
                multi_tenancy_config=SimpleNamespace(enabled=multi_tenancy),
                properties=[SimpleNamespace(name=name, data_type=data_type) for name, data_type in property_types.items()],
                vector_config={"default": SimpleNamespace(vectorizer=SimpleNamespace(vectorizer=vectorizer))},
                vectorizer=None,
            )
        )


class FakeCollections:
    """Track collection lookup and creation calls."""

    def __init__(self, *, exists: bool = True, collection=None) -> None:
        """Initialize the fake collection registry."""
        self._exists = exists
        self.collection = collection or FakeCollection()
        self.create_call = None

    def exists(self, name):
        """Return the configured collection-existence state."""
        return self._exists

    def create(self, name, **kwargs):
        """Record a collection creation call."""
        self.create_call = (name, kwargs)
        self._exists = True

    def get(self, name):
        """Return the configured fake collection."""
        return self.collection


class FakeClient:
    """Provide collection access and track client closure."""

    def __init__(self, collections=None) -> None:
        """Initialize the client with an optional collection registry."""
        self.collections = collections or FakeCollections()
        self.close_calls = 0

    def close(self):
        """Record a client close call."""
        self.close_calls += 1


def _patch_resource_dependencies(monkeypatch, client):
    """Replace external Weaviate and embedding dependencies with fakes."""
    connection_calls = []
    vector_store_call = {}

    def connect_to_custom(**kwargs):
        """Record connection settings and return the fake client."""
        connection_calls.append(kwargs)
        return client

    class VectorStore:
        """Capture vector-store initialization arguments."""

        def __init__(self, **kwargs):
            """Record vector-store constructor arguments."""
            vector_store_call.update(kwargs)

    monkeypatch.setattr(weaviate_init.weaviate, "connect_to_custom", connect_to_custom)
    monkeypatch.setattr(weaviate_init, "WeaviateVectorStore", VectorStore)
    monkeypatch.setattr(weaviate_init, "VoyageAIEmbeddings", lambda **kwargs: object())
    return connection_calls, vector_store_call


def test_initialize_creates_and_reuses_shared_resources(monkeypatch) -> None:
    """Create the collection once and reuse process-wide resources."""
    collections = FakeCollections(exists=False)
    client = FakeClient(collections)
    connection_calls, vector_store_call = _patch_resource_dependencies(monkeypatch, client)
    monkeypatch.setattr(weaviate_init, "_shared_weaviate_resources", None)

    weaviate_init.initialize_weaviate()
    first_resources = weaviate_init.get_weaviate_resources()
    weaviate_init.initialize_weaviate()

    assert weaviate_init.get_weaviate_resources() is first_resources
    assert connection_calls == [
        {
            "http_host": settings.WEAVIATE_HTTP_HOST,
            "http_port": settings.WEAVIATE_HTTP_PORT,
            "http_secure": settings.WEAVIATE_HTTP_SECURE,
            "grpc_host": settings.WEAVIATE_GRPC_HOST,
            "grpc_port": settings.WEAVIATE_GRPC_PORT,
            "grpc_secure": settings.WEAVIATE_GRPC_SECURE,
            "auth_credentials": None,
        }
    ]
    collection_name, create_kwargs = collections.create_call
    assert collection_name == settings.WEAVIATE_COLLECTION
    assert create_kwargs["multi_tenancy_config"].enabled is True
    assert [prop.name for prop in create_kwargs["properties"]] == ["content", "source", "repository_id", "parent_document_id"]
    assert vector_store_call["client"] is client
    assert vector_store_call["use_multi_tenancy"] is True

    weaviate_init.close_weaviate()
    weaviate_init.close_weaviate()
    assert client.close_calls == 1


@pytest.mark.parametrize(
    ("collection", "message"),
    [
        (FakeCollection(multi_tenancy=False), "multi-tenancy"),
        (FakeCollection(properties={weaviate_init.TEXT_PROPERTY: DataType.INT}), "invalid schema"),
        (FakeCollection(vectorizer=Vectorizers.TEXT2VEC_OPENAI), "self-provided vectors"),
    ],
)
def test_invalid_collection_schema_closes_client(monkeypatch, collection, message) -> None:
    """Close a new client when collection validation fails."""
    client = FakeClient(FakeCollections(collection=collection))
    _patch_resource_dependencies(monkeypatch, client)

    with pytest.raises(RuntimeError, match=message):
        weaviate_init._create_weaviate_resources()

    assert client.close_calls == 1


def test_get_resources_requires_startup(monkeypatch) -> None:
    """Reject resource access before application initialization."""
    monkeypatch.setattr(weaviate_init, "_shared_weaviate_resources", None)

    with pytest.raises(RuntimeError, match="not been initialized"):
        weaviate_init.get_weaviate_resources()
