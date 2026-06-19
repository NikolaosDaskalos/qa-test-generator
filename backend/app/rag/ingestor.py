"""Load, split, and persist Git repository documents in Weaviate."""

import logging
import uuid
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import GitLoader
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
from weaviate.classes.query import Filter
from weaviate.classes.tenants import Tenant

from app.core import WeaviateResources, settings
from app.errors.rag_errors import IngestorError
from app.models import RepositoryDocument
from app.persistence import RepositoryDocumentStore

logger = logging.getLogger(__name__)


class DocumentIngestor:
    """Loads an existing local Git clone and stores Python chunks in Weaviate."""

    def __init__(self, resources: WeaviateResources, repository_document_store: RepositoryDocumentStore) -> None:
        """Create an ingestor backed by shared Weaviate resources."""
        self.resources = resources
        self.repository_document_store = repository_document_store

    @cached_property
    def splitter(self) -> RecursiveCharacterTextSplitter:
        """The cached Python-aware splitter, sized by the embedding model's tokenizer."""
        return RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_TOKENIZER),
            separators=RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON),
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

    def ingest(self, repo_path: Path, repository_id: uuid.UUID, branch: str, commit_sha: str, user_id: uuid.UUID) -> int:
        """Replace a Git repository's persisted documents and indexed chunks.

        Returns:
            The number of chunks written to Weaviate.

        """
        logger.info("Repository ingestion started repository_id=%s user_id=%s branch=%s", repository_id, user_id, branch)
        repository_key = str(repository_id)
        tenant = str(user_id).strip()

        raw_docs = self._load(repo_path, branch)
        if not raw_docs:
            logger.error("Repository ingestion found no Python documents for repository_id=%s user_id=%s", repository_id, user_id)
            raise IngestorError("Repository has no Python files")

        # todo sanitize the docs before persist them

        repository_documents = [
            RepositoryDocument(repository_id=repository_id, content=doc.page_content, doc_metadata=doc.metadata | {"commit_sha": commit_sha, "branch": branch})
            for doc in raw_docs
        ]

        self.repository_document_store.replace_for_repository(repository_id, repository_documents)
        logger.info(
            "Repository Documents persisted repository_id=%s user_id=%s branch=%s document_count=%s", repository_id, user_id, branch, len(repository_documents)
        )

        try:
            for raw_doc, repository_document in zip(raw_docs, repository_documents, strict=True):
                raw_doc.metadata.update({"parent_id": str(repository_document.id), "repository_id": repository_key, "branch": branch, "commit_sha": commit_sha})

            chunked_docs = self._split(raw_docs)
            ids = [str(uuid.uuid5(repository_id, f"{commit_sha}:{doc.metadata['source']}:{index}")) for index, doc in enumerate(chunked_docs)]
            self._create_tenant(tenant)
            self._delete_repository_vectors(repository_key, tenant=tenant)
            self._add_documents(chunked_docs, ids=ids, tenant=tenant)
        except Exception:
            self._cleanup_failed_ingestion(repository_id, repository_key=repository_key, tenant=tenant)
            raise

        logger.info(
            f"Repository ingestion completed repository_id={repository_id} user_id={user_id} document_count={len(raw_docs)} chunk_count={len(chunked_docs)}"
        )

        return len(chunked_docs)

    def delete_repository(self, repository_id: uuid.UUID | str, *, user_id: uuid.UUID) -> None:
        """Delete all indexed chunks for a Git repository and user tenant."""
        tenant = str(user_id)
        if not self._tenant_exists(tenant):
            logger.warning("Repository embedding deletion skipped because tenant does not exist repository_id=%s user_id=%s", repository_id, user_id)
            return
        logger.info("Deleting repository embeddings repository_id=%s user_id=%s", repository_id, user_id)
        self._delete_repository_vectors(str(repository_id), tenant=tenant)

    def _add_documents(self, documents: Sequence[Document], *, ids: Sequence[str], tenant: str) -> list[str]:
        """Write documents and IDs to an existing tenant."""
        return self.resources.vector_store.add_documents(list(documents), ids=list(ids), tenant=tenant)

    def _delete_repository_vectors(self, repository_id: str, *, tenant: str) -> None:
        """Delete one Repository's vectors from an existing tenant."""
        self._collection().with_tenant(tenant).data.delete_many(where=Filter.by_property("repository_id").equal(repository_id))

    def _cleanup_failed_ingestion(self, repository_id: uuid.UUID, *, repository_key: str, tenant: str) -> None:
        """Compensate relational and vector writes after failed ingestion."""
        try:
            if self._tenant_exists(tenant):
                self._delete_repository_vectors(repository_key, tenant=tenant)
        except Exception:
            logger.exception("Failed to clean up repository vectors repository_id=%s tenant=%s", repository_id, tenant)
        try:
            self.repository_document_store.delete_by_repository(repository_id)
        except Exception:
            logger.exception("Failed to clean up Repository Documents repository_id=%s", repository_id)

    def _tenant_exists(self, tenant: str) -> bool:
        """Return whether a non-empty tenant already exists."""
        tenant_name = tenant.strip()
        if not tenant_name:
            raise ValueError("tenant cannot be empty")
        return tenant_name in self._collection().tenants.get_by_names([tenant_name])

    def _create_tenant(self, tenant: str) -> None:
        """Create a non-empty tenant when it does not already exist."""
        if not self._tenant_exists(tenant):
            logger.info("Creating Weaviate tenant=%s", tenant)
            self._collection().tenants.create([Tenant(name=tenant)])

    def _collection(self) -> Any:
        """Return the configured Weaviate collection."""
        return self.resources.client.collections.get(settings.WEAVIATE_COLLECTION)

    def _load(self, repo_path: Path, branch: str) -> list[Document]:
        """Load Python files with non-empty content from the checked-out default branch."""
        loader = GitLoader(repo_path=str(repo_path), branch=branch, file_filter=lambda file_path: str(file_path).endswith(".py"))
        raw_docs: list[Document] = [doc for doc in loader.load() if doc.page_content]
        logger.info("Loaded repository Python documents branch=%s document_count=%s", branch, len(raw_docs))
        return raw_docs

    def _split(self, raw_docs: list[Document]) -> list[Document]:
        """Split loaded documents into embedding-sized Python chunks."""
        chunked_docs = self.splitter.split_documents(raw_docs)
        logger.info("Split repository documents document_count=%s chunk_count=%s", len(raw_docs), len(chunked_docs))
        return chunked_docs
