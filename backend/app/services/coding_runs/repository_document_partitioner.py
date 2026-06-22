"""Retrieve and partition Repository Documents for Code Generation Tasks."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.core import settings
from app.db.models import RepositoryDocument
from app.schemas import RetrievalRequest
from app.services.coding_runs.path_safety import confine_candidate_paths


class RepositoryDocumentRetriever(Protocol):
    """Public retrieval boundary used by the partitioner."""

    def retrieve_documents(self, query: str, *, repository_id: uuid.UUID, k: int, alpha: float, parent_limit: int) -> list[RepositoryDocument]: ...


@dataclass(frozen=True)
class RepositoryDocumentPartitionRequest:
    """Inputs needed to retrieve and partition Repository Documents.

    ``checkout_root`` is required: candidate Repository paths are untrusted hints that
    must always be confined against the checkout before entering agent context, so the
    Code Generation path supplies one rather than letting confinement be skipped.
    """

    retrieval_requests: list[RetrievalRequest]
    repository_id: uuid.UUID
    checkout_root: Path | str


@dataclass(frozen=True)
class RepositoryDocumentPartition:
    """Source-code and existing-test Repository Documents plus safe path hints."""

    source_documents: list[RepositoryDocument] = field(default_factory=list)
    test_documents: list[RepositoryDocument] = field(default_factory=list)
    candidate_hints: list[str] = field(default_factory=list)


class RepositoryDocumentPartitioner:
    """Retrieve requests and partition their Repository Documents by type."""

    def __init__(self, retriever: RepositoryDocumentRetriever) -> None:
        self._retriever = retriever

    def partition(self, request: RepositoryDocumentPartitionRequest) -> RepositoryDocumentPartition:
        if not request.checkout_root:
            raise ValueError("A Code Generation partition requires a checkout root to confine candidate paths against.")

        source_documents: list[RepositoryDocument] = []
        test_documents: list[RepositoryDocument] = []
        hints: list[str] = []
        checkout_root = Path(request.checkout_root)

        for retrieval_request in request.retrieval_requests:
            if retrieval_request.candidate_paths:
                hints.extend(confine_candidate_paths(checkout_root, retrieval_request.candidate_paths))
            documents = self._retriever.retrieve_documents(
                retrieval_request.description,
                repository_id=request.repository_id,
                k=settings.TOP_K,
                alpha=settings.HYBRID_SEARCH_ALPHA,
                parent_limit=settings.FINAL_PARENT_LIMIT,
            )
            target = source_documents if retrieval_request.document_type == "source" else test_documents
            target.extend(documents)

        return RepositoryDocumentPartition(source_documents=source_documents, test_documents=test_documents, candidate_hints=list(dict.fromkeys(hints)))
