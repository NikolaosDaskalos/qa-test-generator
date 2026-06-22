"""Test shared Weaviate resource initialization."""

import pytest

from app.core import settings
from app.integrations.weaviate import client as weaviate_client
from app.integrations.weaviate import resources as vector_db


class FakeClient:
    """Track client closure."""

    def __init__(self) -> None:
        """Initialize an open fake client."""
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

    monkeypatch.setattr(weaviate_client.weaviate, "connect_to_custom", connect_to_custom)
    monkeypatch.setattr(vector_db, "WeaviateVectorStore", VectorStore)
    monkeypatch.setattr(vector_db, "VoyageAIEmbeddings", lambda **kwargs: object())
    return connection_calls, vector_store_call


def test_initialize_creates_and_reuses_shared_resources(monkeypatch) -> None:
    """Create and reuse process-wide resources."""
    client = FakeClient()
    connection_calls, vector_store_call = _patch_resource_dependencies(monkeypatch, client)
    monkeypatch.setattr(vector_db, "_shared_weaviate_resources", None)

    vector_db.initialize_weaviate()
    first_resources = vector_db.get_weaviate_resources()
    vector_db.initialize_weaviate()

    assert vector_db.get_weaviate_resources() is first_resources
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
    assert vector_store_call["client"] is client
    assert vector_store_call["use_multi_tenancy"] is True

    vector_db.close_weaviate()
    vector_db.close_weaviate()
    assert client.close_calls == 1


def test_resource_creation_failure_closes_client(monkeypatch) -> None:
    """Close a new client when vector-store setup fails."""
    client = FakeClient()
    _patch_resource_dependencies(monkeypatch, client)
    monkeypatch.setattr(vector_db, "VoyageAIEmbeddings", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("embedding failure")))

    with pytest.raises(RuntimeError, match="embedding failure"):
        vector_db._create_weaviate_resources()

    assert client.close_calls == 1


def test_get_resources_requires_startup(monkeypatch) -> None:
    """Reject resource access before application initialization."""
    monkeypatch.setattr(vector_db, "_shared_weaviate_resources", None)

    with pytest.raises(RuntimeError, match="not been initialized"):
        vector_db.get_weaviate_resources()
