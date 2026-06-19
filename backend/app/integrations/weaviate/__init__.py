"""Weaviate integration: client construction and shared vector-store resources."""

from app.integrations.weaviate.client import METADATA_PROPERTIES, TEXT_PROPERTY, create_weaviate_client
from app.integrations.weaviate.resources import WeaviateResources, close_weaviate, get_weaviate_resources, initialize_weaviate

__all__ = [
    "METADATA_PROPERTIES",
    "TEXT_PROPERTY",
    "create_weaviate_client",
    "WeaviateResources",
    "close_weaviate",
    "get_weaviate_resources",
    "initialize_weaviate",
]
