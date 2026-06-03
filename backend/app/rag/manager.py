"""Management helpers for vector-store records."""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any


DEFAULT_GET_INCLUDE = ("documents", "metadatas")
PARENT_DOCUMENT_ID_KEY = "parent_document_id"


class VectorManager:
    def __init__(self, vectorstore):
        self.vectorstore = vectorstore

    @property
    def collection(self):
        """Expose the wrapped Chroma collection used by LangChain's vector store."""
        return self.vectorstore._collection

    def embedding_exists(self, embedding_id: str) -> bool:
        """Return True when an embedding record exists for the provided Chroma id."""
        if not embedding_id:
            return False

        existing = self.collection.get(ids=[embedding_id], limit=1)
        return bool(existing.get("ids"))

    def get_embeddings_by_parent_id(
        self,
        parent_id: str,
        include: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Return all embedding records whose metadata belongs to a parent document."""
        if not parent_id:
            raise ValueError("parent_id cannot be empty")

        return self.collection.get(
            where={PARENT_DOCUMENT_ID_KEY: parent_id},
            include=list(include or DEFAULT_GET_INCLUDE),
        )

    def delete_embeddings(self, ids: str | Iterable[str]) -> None:
        """Delete embedding records by Chroma id."""
        normalized_ids = self._normalize_ids(ids)
        if not normalized_ids:
            return

        self.vectorstore.delete(ids=normalized_ids)

    def delete_embeddings_by_parent_id(self, parent_id: str) -> None:
        """Delete all embedding records for a parent document id."""
        if not parent_id:
            raise ValueError("parent_id cannot be empty")

        self.collection.delete(where={PARENT_DOCUMENT_ID_KEY: parent_id})

    def upsert_embeddings(
        self,
        documents: Sequence[Any],
        ids: Sequence[str] | None = None,
    ) -> list[str]:
        """Insert or replace embedding records for the provided LangChain documents."""
        if not documents:
            return []

        normalized_ids = self._ids_for_documents(documents, ids)
        return self.vectorstore.add_documents(list(documents), ids=normalized_ids)

    def exists(self, embedding_id: str) -> bool:
        """Alias for embedding_exists."""
        return self.embedding_exists(embedding_id)

    def get_by_parent_id(self, parent_id: str, include: Sequence[str] | None = None) -> dict[str, Any]:
        """Alias for get_embeddings_by_parent_id."""
        return self.get_embeddings_by_parent_id(parent_id, include)

    def upsert(self, documents: Sequence[Any], ids: Sequence[str] | None = None) -> list[str]:
        """Alias for upsert_embeddings."""
        return self.upsert_embeddings(documents, ids)

    def delete(self, ids: str | Iterable[str]) -> None:
        """Alias for delete_embeddings."""
        self.delete_embeddings(ids)

    def check_embeding_exists(self, embedding_id: str) -> bool:
        """Backward-compatible alias for the common misspelling."""
        return self.embedding_exists(embedding_id)

    def get_embedings_by_parent_id(self, parent_id: str, include: Sequence[str] | None = None) -> dict[str, Any]:
        """Backward-compatible alias for the common misspelling."""
        return self.get_embeddings_by_parent_id(parent_id, include)

    def delete_embedings(self, ids: str | Iterable[str]) -> None:
        """Backward-compatible alias for the common misspelling."""
        self.delete_embeddings(ids)

    def upsert_embedings(self, documents: Sequence[Any], ids: Sequence[str] | None = None) -> list[str]:
        """Backward-compatible alias for the common misspelling."""
        return self.upsert_embeddings(documents, ids)

    def _ids_for_documents(self, documents: Sequence[Any], ids: Sequence[str] | None) -> list[str]:
        if ids is not None:
            normalized_ids = list(ids)
            if len(normalized_ids) != len(documents):
                raise ValueError("ids length must match documents length")
            if any(not item_id for item_id in normalized_ids):
                raise ValueError("ids cannot contain empty values")
            return normalized_ids

        return [getattr(document, "id", None) or str(uuid.uuid4()) for document in documents]

    def _normalize_ids(self, ids: str | Iterable[str]) -> list[str]:
        if isinstance(ids, str):
            return [ids] if ids else []

        normalized_ids = list(ids)
        if any(not item_id for item_id in normalized_ids):
            raise ValueError("ids cannot contain empty values")
        return normalized_ids
