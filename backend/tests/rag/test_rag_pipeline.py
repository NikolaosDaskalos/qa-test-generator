"""Test construction of the user-scoped RAG pipeline."""

import uuid
from pathlib import Path

from app.rag import rag_pipeline
from app.rag.rag_pipeline import RAGPipeline


def test_pipeline_constructs_components_from_shared_resources(monkeypatch) -> None:
    """Pass shared Weaviate resources to every pipeline component."""
    resources = object()
    ingestor = object()
    retriever = object()
    llm = object()
    chain_builder = object()
    user_id = uuid.uuid4()

    monkeypatch.setattr(rag_pipeline, "DocumentIngestor", lambda received_resources: (ingestor if received_resources is resources else None))
    monkeypatch.setattr(
        rag_pipeline, "DocumentRetriever", lambda received_resources, tenant: (retriever if (received_resources, tenant) == (resources, str(user_id)) else None)
    )
    monkeypatch.setattr(rag_pipeline, "ChatOpenAI", lambda **kwargs: llm)
    monkeypatch.setattr(
        rag_pipeline,
        "ChainBuilder",
        lambda received_llm, received_retriever: (chain_builder if (received_llm, received_retriever) == (llm, retriever) else None),
    )

    pipeline = RAGPipeline(user_id, resources)

    assert pipeline.weaviate_resources is resources
    assert pipeline.ingestor is ingestor
    assert pipeline.document_retriever is retriever
    assert pipeline.chain_builder is chain_builder
    assert not hasattr(pipeline, "close")


def test_pipeline_ingests_an_exact_repository_snapshot() -> None:
    """Delegate Repository and commit identity to the tenant-aware ingestor."""
    user_id = uuid.uuid4()
    repository_id = uuid.uuid4()
    calls = []

    class FakeIngestor:
        def ingest(self, repo_path, received_repository_id, branch, commit_sha, received_user_id):
            calls.append((repo_path, received_repository_id, branch, commit_sha, received_user_id))
            return 3

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.user_id = user_id
    pipeline.ingestor = FakeIngestor()

    chunk_count = pipeline.ingest(Path("/repo"), repository_id, "main", "a" * 40)

    assert chunk_count == 3
    assert calls == [(Path("/repo"), repository_id, "main", "a" * 40, user_id)]
