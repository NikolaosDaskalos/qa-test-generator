"""Test construction of the user-scoped RAG pipeline."""

import uuid
from pathlib import Path

from pydantic import SecretStr

from app.rag import rag_pipeline
from app.rag.rag_pipeline import RAGPipeline


def test_pipeline_constructs_components_from_shared_resources(monkeypatch) -> None:
    """Pass shared Weaviate resources to every pipeline component."""
    resources = object()
    ingestor = object()
    retriever = object()
    reranker = object()
    llm = object()
    chain_builder = object()
    source_document_store = object()
    user_id = uuid.uuid4()

    monkeypatch.setattr(
        rag_pipeline,
        "DocumentIngestor",
        lambda received_resources, received_store: (ingestor if (received_resources, received_store) == (resources, source_document_store) else None),
    )
    monkeypatch.setattr(
        rag_pipeline,
        "DocumentRetriever",
        lambda received_resources, tenant, received_store, received_reranker: (
            retriever
            if (received_resources, tenant, received_store, received_reranker) == (resources, str(user_id), source_document_store, reranker)
            else None
        ),
    )
    monkeypatch.setattr(
        rag_pipeline,
        "CohereRerank",
        lambda **kwargs: (
            reranker
            if kwargs
            == {
                "model": rag_pipeline.settings.COHERE_RERANK_MODEL,
                "cohere_api_key": SecretStr(rag_pipeline.settings.COHERE_API_KEY),
                "top_n": rag_pipeline.settings.TOP_K,
            }
            else None
        ),
    )
    monkeypatch.setattr(rag_pipeline, "ChatOpenAI", lambda **kwargs: llm)
    monkeypatch.setattr(
        rag_pipeline,
        "ChainBuilder",
        lambda received_llm, received_retriever: (chain_builder if (received_llm, received_retriever) == (llm, retriever) else None),
    )

    pipeline = RAGPipeline(user_id, resources, source_document_store)

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


def test_pipeline_answers_with_repository_scope() -> None:
    """Delegate repository identity and answer options to the chain builder."""
    repository_id = uuid.uuid4()
    history = [{"role": "user", "content": "Earlier question"}]
    stream = object()
    calls = []

    class FakeChainBuilder:
        def answer_stream(self, question, **kwargs):
            calls.append((question, kwargs))
            return stream

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.user_id = uuid.uuid4()
    pipeline.chain_builder = FakeChainBuilder()

    result = pipeline.answer_stream("Current question", repository_id=repository_id, history=history, use_hyde=True)

    assert result is stream
    assert calls == [("Current question", {"repository_id": repository_id, "history": history, "use_hyde": True})]


def test_pipeline_returns_repository_scoped_statistics() -> None:
    """Delegate Repository identity to retrieval statistics."""
    repository_id = uuid.uuid4()
    statistics = {"total_chunks": 2, "unique_sources": 1, "sources": ["app.py"]}
    calls = []

    class FakeRetriever:
        def get_stats(self, *, repository_id):
            calls.append(repository_id)
            return statistics

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.document_retriever = FakeRetriever()

    assert pipeline.get_stats(repository_id=repository_id) is statistics
    assert calls == [repository_id]
