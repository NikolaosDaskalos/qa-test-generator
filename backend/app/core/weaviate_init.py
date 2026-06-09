"""Create, validate, and manage shared Weaviate application resources."""

from dataclasses import dataclass
from threading import Lock
from typing import Any

import weaviate
from langchain_voyageai import VoyageAIEmbeddings
from langchain_weaviate.vectorstores import WeaviateVectorStore
from pydantic import SecretStr
from weaviate.auth import Auth
from weaviate.classes.config import Configure, DataType, Property, Vectorizers
from weaviate.client import WeaviateClient

from app.core.config import settings

TEXT_PROPERTY = "content"
METADATA_PROPERTIES = ("source", "repository_id", "parent_document_id")


@dataclass(frozen=True)
class WeaviateResources:
    """Objects that share one Weaviate client lifecycle."""

    client: WeaviateClient
    vector_store: WeaviateVectorStore


_shared_weaviate_resources: WeaviateResources | None = None
_weaviate_lock = Lock()


def initialize_weaviate() -> None:
    """Create the process-wide client and ensure its collection exists."""
    global _shared_weaviate_resources

    with _weaviate_lock:
        if _shared_weaviate_resources is None:
            _shared_weaviate_resources = _create_weaviate_resources()


def get_weaviate_resources() -> WeaviateResources:
    """Return the resources initialized during application startup."""
    if _shared_weaviate_resources is None:
        raise RuntimeError("Weaviate has not been initialized")
    return _shared_weaviate_resources


def close_weaviate() -> None:
    """Close the shared client once, if it was initialized."""
    global _shared_weaviate_resources

    with _weaviate_lock:
        resources = _shared_weaviate_resources
        _shared_weaviate_resources = None

    if resources is not None:
        resources.client.close()


def _create_weaviate_resources() -> WeaviateResources:
    """Connect to Weaviate and construct the shared vector store.

    Returns:
        The initialized client and vector-store resources.

    Raises:
        Exception: Propagates connection, schema, or embedding setup failures
            after closing the newly created client.

    """
    auth_credentials = Auth.api_key(settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None
    client = weaviate.connect_to_custom(
        http_host=settings.WEAVIATE_HTTP_HOST,
        http_port=settings.WEAVIATE_HTTP_PORT,
        http_secure=settings.WEAVIATE_HTTP_SECURE,
        grpc_host=settings.WEAVIATE_GRPC_HOST,
        grpc_port=settings.WEAVIATE_GRPC_PORT,
        grpc_secure=settings.WEAVIATE_GRPC_SECURE,
        auth_credentials=auth_credentials,
    )

    try:
        _get_or_create_collection(client)
        embeddings = VoyageAIEmbeddings(
            model=settings.EMBEDDING_MODEL, output_dimension=settings.EMBEDDING_DIMENSIONS, api_key=SecretStr(settings.VOYAGE_API_KEY)
        )
        vector_store = WeaviateVectorStore(
            client=client,
            index_name=settings.WEAVIATE_COLLECTION,
            text_key=TEXT_PROPERTY,
            embedding=embeddings,
            attributes=list(METADATA_PROPERTIES),
            use_multi_tenancy=True,
        )
        return WeaviateResources(client=client, vector_store=vector_store)
    except Exception:
        client.close()
        raise


def _get_or_create_collection(client: WeaviateClient) -> None:
    """Create the configured collection when absent, then validate it."""
    if not client.collections.exists(settings.WEAVIATE_COLLECTION):
        client.collections.create(
            settings.WEAVIATE_COLLECTION,
            properties=[Property(name=TEXT_PROPERTY, data_type=DataType.TEXT), *[Property(name=name, data_type=DataType.TEXT) for name in METADATA_PROPERTIES]],
            vector_config=Configure.Vectors.self_provided(),
            multi_tenancy_config=Configure.multi_tenancy(enabled=True),
        )

    collection = client.collections.get(settings.WEAVIATE_COLLECTION)
    _validate_collection(collection)


def _validate_collection(collection: Any) -> None:
    """Validate collection tenancy, properties, and vectorizer settings.

    Raises:
        RuntimeError: If the existing collection is incompatible.

    """
    config = collection.config.get()
    if not config.multi_tenancy_config.enabled:
        raise RuntimeError(f"Weaviate collection {settings.WEAVIATE_COLLECTION!r} must enable multi-tenancy")

    properties = {prop.name: prop.data_type for prop in config.properties}
    expected_properties = {TEXT_PROPERTY: DataType.TEXT, **dict.fromkeys(METADATA_PROPERTIES, DataType.TEXT)}
    invalid_properties = [name for name, expected_type in expected_properties.items() if properties.get(name) != expected_type]
    if invalid_properties:
        raise RuntimeError(f"Weaviate collection {settings.WEAVIATE_COLLECTION!r} has an invalid schema for properties: {', '.join(invalid_properties)}")

    vectorizers: list[Any] = []
    if config.vector_config:
        vectorizers.extend(named_vector.vectorizer.vectorizer for named_vector in config.vector_config.values())
    elif config.vectorizer is not None:
        vectorizers.append(config.vectorizer)

    if not vectorizers or any(vectorizer not in (Vectorizers.NONE, Vectorizers.NONE.value) for vectorizer in vectorizers):
        raise RuntimeError(f"Weaviate collection {settings.WEAVIATE_COLLECTION!r} must use self-provided vectors")
