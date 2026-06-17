"""Dependency seam tests for application service composition."""

import uuid
from types import SimpleNamespace

from app import dependencies


def test_session_graph_uses_direct_rag_components(monkeypatch) -> None:
    """The session graph is built from the model and retriever, not a RAG facade."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_checkpointer=object())))
    chat_model = object()
    retriever = object()
    coding_run_store = object()
    repository_store = object()
    graph = object()
    captured = {}

    def fake_build_graph(**kwargs):
        captured.update(kwargs)
        return graph

    monkeypatch.setattr(dependencies, "build_graph", fake_build_graph)

    result = dependencies.get_session_graph(
        request=request,
        chat_model=chat_model,
        document_retriever=retriever,
        coding_run_store=coding_run_store,
        repository_store=repository_store,
    )

    assert result is graph
    assert captured["classifier_llm"] is chat_model
    assert captured["retriever"] is retriever
    assert captured["llm"] is chat_model
    assert captured["planner_llm"] is chat_model
    assert captured["checkpointer"] is request.app.state.session_checkpointer


def test_document_retriever_is_scoped_to_current_user(monkeypatch) -> None:
    """The retriever provider binds retrieval to the authenticated user's tenant."""
    user = SimpleNamespace(id=uuid.uuid4())
    weaviate_resources = object()
    source_document_store = object()
    reranker = object()
    retriever = object()
    captured = {}

    def fake_reranker(**kwargs):
        captured["reranker_kwargs"] = kwargs
        return reranker

    def fake_retriever(resources, tenant, store, received_reranker):
        captured["retriever_args"] = (resources, tenant, store, received_reranker)
        return retriever

    monkeypatch.setattr(dependencies, "CohereRerank", fake_reranker)
    monkeypatch.setattr(dependencies, "DocumentRetriever", fake_retriever)

    result = dependencies.get_document_retriever(user, weaviate_resources, source_document_store)

    assert result is retriever
    assert captured["retriever_args"] == (
        weaviate_resources,
        str(user.id),
        source_document_store,
        reranker,
    )
    assert captured["reranker_kwargs"]["model"] == dependencies.settings.COHERE_RERANK_MODEL
    assert captured["reranker_kwargs"]["top_n"] == dependencies.settings.TOP_K
