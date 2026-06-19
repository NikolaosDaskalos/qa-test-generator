"""Core infrastructure: config, database, security, vector store, re-exported as one surface."""

from app.core.checkpointer import close_checkpointer, open_checkpointer
from app.core.config import PROJECT_PATH, Settings, settings
from app.core.db import engine, init_db
from app.core.security import ALGORITHM, create_access_token, decrypt_repository_token, encrypt_repository_token, get_password_hash, verify_password
from app.core.vector_db import WeaviateResources, close_weaviate, get_weaviate_resources, initialize_weaviate
from app.core.weaviate_client import METADATA_PROPERTIES, TEXT_PROPERTY, create_weaviate_client

__all__ = [
    "PROJECT_PATH",
    "Settings",
    "settings",
    "ALGORITHM",
    "create_access_token",
    "decrypt_repository_token",
    "encrypt_repository_token",
    "get_password_hash",
    "verify_password",
    "engine",
    "init_db",
    "METADATA_PROPERTIES",
    "TEXT_PROPERTY",
    "create_weaviate_client",
    "WeaviateResources",
    "close_weaviate",
    "get_weaviate_resources",
    "initialize_weaviate",
    "close_checkpointer",
    "open_checkpointer",
]
