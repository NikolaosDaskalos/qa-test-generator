"""Create and manage shared Weaviate application resources."""

from dataclasses import dataclass
from threading import Lock

from langchain_voyageai import VoyageAIEmbeddings
from langchain_weaviate.vectorstores import WeaviateVectorStore
from pydantic import SecretStr
from weaviate.client import WeaviateClient

from app.core.config import settings
from app.core.weaviate_client import METADATA_PROPERTIES, TEXT_PROPERTY, create_weaviate_client


@dataclass(frozen=True)
class WeaviateResources:
    """Objects that share one Weaviate client lifecycle."""

    client: WeaviateClient
    vector_store: WeaviateVectorStore


_shared_weaviate_resources: WeaviateResources | None = None
_weaviate_lock = Lock()


def initialize_weaviate() -> None:
    """Create the process-wide Weaviate client and vector store."""
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
    """Connect to Weaviate and construct the shared vector store."""
    client = create_weaviate_client()

    try:
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
