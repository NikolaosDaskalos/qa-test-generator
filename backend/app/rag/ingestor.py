"""Load, split, and persist Git repository documents in Weaviate."""

import logging
import os
import uuid
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import GitLoader
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
from weaviate.classes.query import Filter
from weaviate.classes.tenants import Tenant

from app.core.config import settings
from app.core.vector_db import WeaviateResources

logger = logging.getLogger(__name__)

# Avoid the warning emitted when the tokenizer receives a token only as an argument.
os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)


class DocumentIngestor:
    """Loads an existing local Git clone and stores Python chunks in Weaviate."""

    def __init__(self, resources: WeaviateResources) -> None:
        """Create an ingestor backed by shared Weaviate resources."""
        self.resources = resources

    def ingest(self, repo_path: Path, repository_id: uuid.UUID, branch: str, commit_sha: str, user_id: uuid.UUID) -> int:
        """Replace a Git repository's indexed chunks for one user tenant.

        Returns:
            The number of chunks written to Weaviate.

        """
        logger.info("Repository ingestion started repository_id=%s user_id=%s branch=%s", repository_id, user_id, branch)
        raw_docs = self._load(repo_path, branch)
        repository_key = str(repository_id)
        for raw_doc in raw_docs:
            source = raw_doc.metadata["source"]
            raw_doc.metadata.update(
                {"repository_id": repository_key, "commit_sha": commit_sha, "parent_document_id": str(uuid.uuid5(repository_id, f"{commit_sha}:{source}"))}
            )
        chunked_docs = self._split(raw_docs) if raw_docs else []
        tenant = str(user_id)

        self._ensure_tenant(tenant)
        self._delete_by_repository(repository_key, tenant=tenant)
        if not chunked_docs:
            logger.warning("Repository ingestion found no Python documents repository_id=%s user_id=%s", repository_id, user_id)
            return 0

        ids = [str(uuid.uuid5(repository_id, f"{commit_sha}:{doc.metadata['source']}:{index}")) for index, doc in enumerate(chunked_docs)]
        self._add_documents(chunked_docs, ids=ids, tenant=tenant)
        logger.info(
            "Repository ingestion completed repository_id=%s user_id=%s document_count=%s chunk_count=%s",
            repository_id,
            user_id,
            len(raw_docs),
            len(chunked_docs),
        )
        return len(chunked_docs)

    def add_documents(self, documents: Sequence[Document], *, ids: Sequence[str], user_id: uuid.UUID) -> list[str]:
        """Add documents with caller-provided IDs to a user's tenant.

        Raises:
            ValueError: If IDs are missing or do not match the documents.

        """
        if not documents:
            logger.warning("Document add skipped because no documents were provided user_id=%s", user_id)
            return []
        if len(ids) != len(documents):
            logger.warning(
                "Document add rejected because ID and document counts differ user_id=%s id_count=%s document_count=%s", user_id, len(ids), len(documents)
            )
            raise ValueError("ids length must match documents length")
        if any(not embedding_id for embedding_id in ids):
            logger.warning("Document add rejected because an embedding ID is empty user_id=%s", user_id)
            raise ValueError("ids cannot contain empty values")

        tenant = str(user_id)
        self._ensure_tenant(tenant)
        added_ids = self._add_documents(documents, ids=ids, tenant=tenant)
        logger.info("Documents added user_id=%s document_count=%s", user_id, len(documents))
        return added_ids

    def delete_by_repository(self, repository_id: uuid.UUID | str, *, user_id: uuid.UUID) -> None:
        """Delete all indexed chunks for a Git repository and user tenant."""
        tenant = str(user_id)
        if not self._tenant_exists(tenant):
            logger.warning("Repository embedding deletion skipped because tenant does not exist repository_id=%s user_id=%s", repository_id, user_id)
            return
        logger.info("Deleting repository embeddings repository_id=%s user_id=%s", repository_id, user_id)
        self._delete_by_repository(str(repository_id), tenant=tenant)

    def delete_embeddings(self, ids: str | Iterable[str], *, user_id: uuid.UUID) -> None:
        """Delete one or more embedding objects from a user's tenant.

        Raises:
            ValueError: If any supplied embedding ID is empty.

        """
        normalized_ids = [ids] if isinstance(ids, str) else list(ids)
        if not normalized_ids:
            logger.warning("Embedding deletion skipped because no IDs were provided user_id=%s", user_id)
            return
        if any(not embedding_id for embedding_id in normalized_ids):
            logger.warning("Embedding deletion rejected because an ID is empty user_id=%s", user_id)
            raise ValueError("ids cannot contain empty values")

        tenant = str(user_id)
        self._ensure_tenant(tenant)
        self.resources.vector_store.delete(ids=normalized_ids, tenant=tenant)
        logger.info("Embeddings deleted user_id=%s embedding_count=%s", user_id, len(normalized_ids))

    def delete_embeddings_by_parent_id(self, parent_id: str, *, user_id: uuid.UUID) -> None:
        """Delete chunks associated with a parent document.

        Raises:
            ValueError: If the parent document ID is empty.

        """
        if not parent_id:
            logger.warning("Parent embedding deletion rejected because parent_id is empty user_id=%s", user_id)
            raise ValueError("parent_id cannot be empty")

        tenant = str(user_id)
        self._ensure_tenant(tenant)
        self._collection().with_tenant(tenant).data.delete_many(where=Filter.by_property("parent_document_id").equal(parent_id))
        logger.info("Parent embeddings deleted user_id=%s parent_id=%s", user_id, parent_id)

    def _add_documents(self, documents: Sequence[Document], *, ids: Sequence[str], tenant: str) -> list[str]:
        """Write documents and IDs to an existing tenant."""
        return self.resources.vector_store.add_documents(list(documents), ids=list(ids), tenant=tenant)

    def _delete_by_repository(self, repository_id: str, *, tenant: str) -> None:
        """Delete Git repository objects from an existing tenant."""
        self._collection().with_tenant(tenant).data.delete_many(where=Filter.by_property("repository_id").equal(repository_id))

    def _ensure_tenant(self, tenant: str) -> None:
        """Create a non-empty tenant when it does not already exist."""
        tenant_name = tenant.strip()
        if not tenant_name:
            raise ValueError("tenant cannot be empty")
        collection = self._collection()
        if tenant_name not in collection.tenants.get_by_names([tenant_name]):
            logger.info("Creating Weaviate tenant=%s", tenant_name)
            collection.tenants.create([Tenant(name=tenant_name)])

    def _tenant_exists(self, tenant: str) -> bool:
        """Return whether a non-empty tenant already exists."""
        tenant_name = tenant.strip()
        if not tenant_name:
            raise ValueError("tenant cannot be empty")
        return tenant_name in self._collection().tenants.get_by_names([tenant_name])

    def _collection(self) -> Any:
        """Return the configured Weaviate collection."""
        return self.resources.client.collections.get(settings.WEAVIATE_COLLECTION)

    def _load(self, repo_path: Path, branch: str) -> list[Document]:
        """Load Python files from the checked-out default branch."""
        loader = GitLoader(repo_path=str(repo_path), branch=branch, file_filter=lambda file_path: str(file_path).endswith(".py"))
        raw_docs: list[Document] = loader.load()
        logger.info("Loaded repository Python documents branch=%s document_count=%s", branch, len(raw_docs))
        return raw_docs

    def _split(self, raw_docs: list[Document]) -> list[Document]:
        """Split loaded documents into embedding-sized Python chunks."""
        splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_TOKENIZER),
            separators=RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON),
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        chunked_docs = splitter.split_documents(raw_docs)
        logger.info("Split repository documents document_count=%s chunk_count=%s", len(raw_docs), len(chunked_docs))
        return chunked_docs
