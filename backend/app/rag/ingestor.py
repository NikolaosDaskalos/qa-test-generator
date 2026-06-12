"""Load, split, and persist Git repository documents in Weaviate."""

import logging
import os
import uuid
from collections.abc import Iterable, Sequence
from functools import cached_property
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
from app.errors.ingestor_errors import IngestorError

from app.models import SourceDocument
from dependencies import SourceDocumentStoreDep

logger = logging.getLogger(__name__)

# Avoid the warning emitted when the tokenizer receives a token only as an argument.
os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)


class DocumentIngestor:
    """Loads an existing local Git clone and stores Python chunks in Weaviate."""

    def __init__(self, resources: WeaviateResources, source_document_store: SourceDocumentStoreDep) -> None:
        """Create an ingestor backed by shared Weaviate resources."""
        self.resources = resources
        self.source_document_store = source_document_store

    @cached_property
    def splitter(self) -> RecursiveCharacterTextSplitter:
        return RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_TOKENIZER),
            separators=RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON),
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

    def ingest(self, repo_path: Path, repository_id: uuid.UUID, branch: str, commit_sha: str, user_id: uuid.UUID) -> int:
        """Add a Git repository's indexed chunks for one user tenant.
        This should be used only the first time a repository is ingested.

        Returns:
            The number of chunks written to Weaviate.

        """
        logger.info("Repository ingestion started repository_id=%s user_id=%s branch=%s", repository_id, user_id, branch)
        repo_id_str = str(repository_id)
        tenant = str(user_id).strip()

        raw_docs = self._load(repo_path, branch)
        if not raw_docs:
            logger.error("Repository ingestion found no Python documents for repository_id=%s user_id=%s", repository_id, user_id)
            IngestorError(f"Repository has no python files")

        # todo sanitize the docs before persist them

        source_docs: list[SourceDocument] = [
            SourceDocument(
                repository_id=repository_id,
                content=doc.page_content,
                doc_metadata=doc.metadata | {"commit_sha": commit_sha}
            )
            for doc in raw_docs
        ]

        self.source_document_store.save_all(source_docs)
        logger.info(
            f"Source Documents persisted to database for repository_id={repository_id} user_id={user_id} branch={branch} document_count={len(source_docs)}")
        for raw_doc, source_doc in (zip(raw_docs, source_docs)):
            raw_doc.metadata.update({
                "parent_id": source_doc.id,
                "repository_id": str(source_doc.repository_id),
                "commit_sha": source_doc.doc_metadata["commit_sha"],
            })

        chunked_docs = self._split(raw_docs)

        self._create_tenant(tenant)

        ids = [str(uuid.uuid4()) for _ in chunked_docs]
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
        self._create_tenant(tenant)
        added_ids = self._add_documents(documents, ids=ids, tenant=tenant)
        logger.info("Documents added user_id=%s document_count=%s", user_id, len(documents))
        return added_ids

    def delete_repository(self, repository_id: uuid.UUID | str, *, user_id: uuid.UUID) -> None:
        """Delete all indexed chunks for a Git repository and user tenant."""
        tenant = str(user_id)
        if not self._tenant_exists(tenant):
            logger.warning("Repository embedding deletion skipped because tenant does not exist repository_id=%s user_id=%s", repository_id, user_id)
            return
        logger.info("Deleting repository embeddings repository_id=%s user_id=%s", repository_id, user_id)
        self._collection().with_tenant(tenant).data.delete_many(where=Filter.by_property("repository_id").equal(repository_id))

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
        self._create_tenant(tenant)
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
        self._create_tenant(tenant)
        self._collection().with_tenant(tenant).data.delete_many(where=Filter.by_property("parent_id").equal(parent_id))
        logger.info("Parent embeddings deleted user_id=%s parent_id=%s", user_id, parent_id)

    def _add_documents(self, documents: Sequence[Document], *, ids: Sequence[str], tenant: str) -> list[str]:
        """Write documents and IDs to an existing tenant."""
        return self.resources.vector_store.add_documents(list(documents), ids=list(ids), tenant=tenant)

    def _repository_exists(self, repository_id: uuid.UUID, tenant: str) -> bool:
        """Check if a repository exists."""
        result = self._collection().with_tenant(tenant).query.fetch_objects(
            filters=Filter.by_property("repository_id").equal(str(repository_id)), limit=1)
        return result.total_count > 0

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
