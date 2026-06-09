"""Test construction of the user-scoped RAG pipeline."""

import uuid

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
