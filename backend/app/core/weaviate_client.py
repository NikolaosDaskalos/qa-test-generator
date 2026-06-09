"""Create configured Weaviate clients without loading vector-store dependencies."""

import weaviate
from weaviate.auth import Auth
from weaviate.client import WeaviateClient

from app.core.config import settings

TEXT_PROPERTY = "content"
METADATA_PROPERTIES = ("source", "repository_id", "parent_document_id")


def create_weaviate_client() -> WeaviateClient:
    """Connect to the configured Weaviate instance."""
    auth_credentials = Auth.api_key(settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None
    return weaviate.connect_to_custom(
        http_host=settings.WEAVIATE_HTTP_HOST,
        http_port=settings.WEAVIATE_HTTP_PORT,
        http_secure=settings.WEAVIATE_HTTP_SECURE,
        grpc_host=settings.WEAVIATE_GRPC_HOST,
        grpc_port=settings.WEAVIATE_GRPC_PORT,
        grpc_secure=settings.WEAVIATE_GRPC_SECURE,
        auth_credentials=auth_credentials,
    )
