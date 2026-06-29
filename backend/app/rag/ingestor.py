"""Load, split, and persist Git repository documents in Weaviate."""

import logging
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import GitLoader
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
from weaviate.classes.query import Filter
from weaviate.classes.tenants import Tenant

from app.core import settings
from app.core.errors.rag_errors import IngestorError
from app.db.models import RepositoryDocument
from app.db.persistence import RepositoryDocumentStore
from app.integrations.weaviate import WeaviateResources

logger = logging.getLogger(__name__)

# Committed-but-unwanted files GitLoader cannot filter on its own: dependency lock files and
# vendored source trees that bloat the index without aiding retrieval or test generation.
_LOCK_FILE_NAMES = frozenset({"poetry.lock", "package-lock.json", "yarn.lock", "Cargo.lock"})
_LOCK_FILE_SUFFIX = ".lock"
_VENDOR_DIRECTORIES = frozenset({"vendor", "third_party", "node_modules"})


@dataclass(frozen=True)
class _FileType:
    """A file's resolved chunking language and derived content category.

    `language` is ``None`` for files that have no language-aware splitter and fall back to the
    generic recursive splitter. `category` is one of ``code``/``config``/``docs``/``other``.
    """

    language: Language | None
    category: str


# A single extension/filename table drives both per-language chunking and the derived category
# stamped onto each Repository Document and Code Chunk (ADR 0012). New file types are added as rows;
# anything unmapped falls back to the generic splitter and the ``other`` category.
_DEFAULT_FILE_TYPE = _FileType(language=None, category="other")
_EXTENSION_FILE_TYPES: dict[str, _FileType] = {
    ".py": _FileType(language=Language.PYTHON, category="code"),
    ".md": _FileType(language=Language.MARKDOWN, category="docs"),
    ".toml": _FileType(language=None, category="config"),
}
_FILENAME_FILE_TYPES: dict[str, _FileType] = {}


def _file_type_for(source: str) -> _FileType:
    """Resolve a file's chunking language and category from its name, defaulting to generic/other."""
    path = Path(source)
    if path.name in _FILENAME_FILE_TYPES:
        return _FILENAME_FILE_TYPES[path.name]
    return _EXTENSION_FILE_TYPES.get(path.suffix.lower(), _DEFAULT_FILE_TYPE)


class DocumentIngestor:
    """Loads an existing local Git clone and stores committed text-file chunks in Weaviate."""

    def __init__(self, resources: WeaviateResources, repository_document_store: RepositoryDocumentStore) -> None:
        """Create an ingestor backed by shared Weaviate resources."""
        self.resources = resources
        self.repository_document_store = repository_document_store
        self._splitters: dict[Language | None, RecursiveCharacterTextSplitter] = {}

    @cached_property
    def _tokenizer(self) -> Any:
        """The cached embedding-model tokenizer that sizes every splitter's chunks."""
        return AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_TOKENIZER)

    def _splitter_for(self, language: Language | None) -> RecursiveCharacterTextSplitter:
        """Return the cached splitter for a language, building it once on first use.

        A ``Language`` uses that language's recursive separators; ``None`` falls back to the plain
        generic recursive splitter. Every splitter shares the same chunk size, overlap, and
        embedding-model tokenizer sizing.
        """
        if language not in self._splitters:
            separators = RecursiveCharacterTextSplitter.get_separators_for_language(language) if language is not None else None
            self._splitters[language] = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
                tokenizer=self._tokenizer,
                separators=separators,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )
        return self._splitters[language]

    def ingest(self, repo_path: Path, repository_id: uuid.UUID, branch: str, commit_sha: str, user_id: uuid.UUID) -> int:
        """Replace a Git repository's persisted documents and indexed chunks.

        Returns:
            The number of chunks written to Weaviate.

        """
        logger.info("Repository ingestion started repository_id=%s user_id=%s branch=%s", repository_id, user_id, branch)
        repository_key = str(repository_id)
        tenant = str(user_id).strip()

        raw_docs = self._load(repo_path, branch)
        if not any(self._is_python(doc) for doc in raw_docs):
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
        """Load every committed UTF-8 text file with non-empty content from the checked-out branch."""
        loader = GitLoader(repo_path=str(repo_path), branch=branch, file_filter=self._file_filter)
        raw_docs: list[Document] = [doc for doc in loader.load() if doc.page_content]
        for doc in raw_docs:
            file_type = _file_type_for(str(doc.metadata.get("source", "")))
            doc.metadata["category"] = file_type.category
            doc.metadata["language"] = file_type.language.value if file_type.language is not None else "text"
        logger.info("Loaded repository documents branch=%s document_count=%s", branch, len(raw_docs))
        return raw_docs

    def _file_filter(self, file_path: str) -> bool:
        """Accept committed text files within the size cap and outside the lock/vendor denylist.

        GitLoader already excludes binaries (UTF-8 decode) and git-ignored paths; this adds the
        two guards it lacks: a byte cap checked before reading, and a small lock/vendor denylist.
        """
        path = Path(file_path)
        if path.name in _LOCK_FILE_NAMES or path.suffix == _LOCK_FILE_SUFFIX:
            logger.debug("Skipping lock file path=%s", file_path)
            return False
        if _VENDOR_DIRECTORIES.intersection(path.parts):
            logger.debug("Skipping vendored file path=%s", file_path)
            return False
        if os.path.getsize(file_path) > settings.MAX_INGEST_FILE_BYTES:
            logger.debug("Skipping oversized file path=%s", file_path)
            return False
        return True

    @staticmethod
    def _is_python(doc: Document) -> bool:
        """Return whether a loaded document is a Python source file."""
        return str(doc.metadata.get("source", "")).endswith(".py")

    def _split(self, raw_docs: list[Document]) -> list[Document]:
        """Split documents into embedding-sized chunks, grouping by resolved chunking language.

        Each document routes to its language's splitter (``.py`` keeps Python separators, recognized
        markup uses its own, everything else falls back to the generic splitter). Documents are
        grouped so each language's splitter is invoked once, in first-appearance order.
        """
        grouped: dict[Language | None, list[Document]] = {}
        for doc in raw_docs:
            language = _file_type_for(str(doc.metadata.get("source", ""))).language
            grouped.setdefault(language, []).append(doc)

        chunked_docs: list[Document] = []
        for language, docs in grouped.items():
            chunked_docs.extend(self._splitter_for(language).split_documents(docs))
        logger.info("Split repository documents document_count=%s chunk_count=%s", len(raw_docs), len(chunked_docs))
        return chunked_docs
