"""Deep Repository Evidence partitioner for test generation."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.services.coding_runs.path_safety import confine_candidate_paths
from app.core.config import settings
from app.models.source_document import SourceDocument
from app.schemas.research_intent import ResearchIntent


class EvidenceRetriever(Protocol):
    """Retriever boundary used by the evidence partitioner."""

    def retrieve_evidence(self, query: str, *, repository_id: uuid.UUID, k: int, alpha: float, parent_limit: int) -> list[SourceDocument]:
        """Return Repository Evidence for one Research Intent."""
        ...


@dataclass(frozen=True)
class EvidencePartitionRequest:
    """Plain inputs needed to retrieve and partition Repository Evidence."""

    research_intents: list[ResearchIntent]
    repository_id: uuid.UUID
    checkout_root: Path | str | None = None


@dataclass(frozen=True)
class EvidencePartition:
    """Partitioned Repository Evidence and validated candidate hints."""

    source_evidence: list[SourceDocument] = field(default_factory=list)
    test_evidence: list[SourceDocument] = field(default_factory=list)
    candidate_hints: list[str] = field(default_factory=list)


class EvidencePartitioner:
    """Retrieve each Research Intent and partition the resulting Repository Evidence."""

    def __init__(self, retriever: EvidenceRetriever) -> None:
        self._retriever = retriever

    def partition(self, request: EvidencePartitionRequest) -> EvidencePartition:
        source_evidence: list[SourceDocument] = []
        test_evidence: list[SourceDocument] = []
        hints: list[str] = []

        for intent in request.research_intents:
            if request.checkout_root and intent.candidate_paths:
                hints.extend(confine_candidate_paths(Path(request.checkout_root), intent.candidate_paths))
            evidence = self._retriever.retrieve_evidence(
                intent.description,
                repository_id=request.repository_id,
                k=settings.TOP_K,
                alpha=settings.HYBRID_SEARCH_ALPHA,
                parent_limit=settings.FINAL_PARENT_LIMIT,
            )
            target = source_evidence if intent.target == "source" else test_evidence
            target.extend(evidence)

        return EvidencePartition(source_evidence=source_evidence, test_evidence=test_evidence, candidate_hints=_dedupe(hints))


def _dedupe(values: list[str]) -> list[str]:
    """Return values in first-seen order."""
    return list(dict.fromkeys(values))
