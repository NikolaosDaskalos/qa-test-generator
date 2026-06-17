"""Evidence partitioning from plain Research Intents."""

import uuid

from app.services.coding_runs.evidence_partitioner import EvidencePartitioner, EvidencePartitionRequest
from app.models.source_document import SourceDocument
from app.schemas.research_intent import ResearchIntent


class QueryRetriever:
    """Return Repository Evidence by query and record retrieval calls."""

    def __init__(self, by_query: dict[str, list[SourceDocument]]) -> None:
        self.by_query = by_query
        self.calls: list[tuple[str, dict[str, object]]] = []

    def retrieve_evidence(self, query: str, *, repository_id: uuid.UUID, k: int, alpha: float, parent_limit: int) -> list[SourceDocument]:
        self.calls.append((query, {"repository_id": repository_id, "k": k, "alpha": alpha, "parent_limit": parent_limit}))
        return self.by_query.get(query, [])


def _source(repository_id: uuid.UUID, source: str, content: str = "evidence") -> SourceDocument:
    return SourceDocument(repository_id=repository_id, content=content, doc_metadata={"source": source})


def test_partition_routes_retrieved_evidence_by_research_intent_target() -> None:
    """Research Intents retrieve under the Repository and route source vs. test evidence."""
    repository_id = uuid.uuid4()
    retriever = QueryRetriever(
        {
            "auth implementation": [_source(repository_id, "app/auth.py", "impl")],
            "auth tests": [_source(repository_id, "tests/test_auth.py", "test")],
        }
    )
    partitioner = EvidencePartitioner(retriever)

    result = partitioner.partition(
        EvidencePartitionRequest(
            research_intents=[
                ResearchIntent(target="source", description="auth implementation"),
                ResearchIntent(target="test", description="auth tests"),
            ],
            repository_id=repository_id,
        )
    )

    assert [doc.doc_metadata["source"] for doc in result.source_evidence] == ["app/auth.py"]
    assert [doc.doc_metadata["source"] for doc in result.test_evidence] == ["tests/test_auth.py"]
    assert [call[1]["repository_id"] for call in retriever.calls] == [repository_id, repository_id]


def test_partition_confines_and_deduplicates_candidate_hints_in_first_seen_order(tmp_path) -> None:
    """Candidate path hints are confined to the checkout and de-duplicated in first-seen order."""
    partitioner = EvidencePartitioner(QueryRetriever({}))

    result = partitioner.partition(
        EvidencePartitionRequest(
            research_intents=[
                ResearchIntent(target="source", description="auth", candidate_paths=["app/auth.py", "/etc/passwd", "tests/test_auth.py"]),
                ResearchIntent(target="test", description="auth tests", candidate_paths=["app/./auth.py", "../escape", "tests/test_auth.py"]),
            ],
            repository_id=uuid.uuid4(),
            checkout_root=tmp_path,
        )
    )

    assert result.candidate_hints == ["app/auth.py", "tests/test_auth.py"]
