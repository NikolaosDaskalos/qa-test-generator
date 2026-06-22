"""Dependency seam tests for application service composition."""

import uuid
from types import SimpleNamespace

from app import dependencies


def test_session_graph_uses_direct_rag_components(monkeypatch) -> None:
    """The session graph is built from the model and retriever, not a RAG facade."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_checkpointer=object())))
    chat_model = object()
    strong_chat_model = object()
    strongest_chat_model = object()
    retriever = object()
    coding_run_store = object()
    repository_store = object()
    graph = object()
    captured = {}

    def fake_build_graph(**kwargs):
        captured.update(kwargs)
        return graph

    monkeypatch.setattr(dependencies, "build_graph", fake_build_graph)
    monkeypatch.setattr(dependencies, "CodeGenerator", lambda model: ("code_generator", model))
    monkeypatch.setattr(dependencies, "CodeReviewer", lambda model: ("code_reviewer", model))

    result = dependencies.get_session_graph(
        request=request,
        chat_model=chat_model,
        strong_chat_model=strong_chat_model,
        strongest_chat_model=strongest_chat_model,
        document_retriever=retriever,
        coding_run_store=coding_run_store,
        repository_store=repository_store,
    )

    assert result is graph
    assert captured["classifier_llm"] is chat_model
    assert captured["retriever"] is retriever
    assert captured["llm"] is chat_model
    assert captured["planner_llm"] is chat_model
    assert captured["code_generator"] == ("code_generator", strong_chat_model)
    assert captured["code_reviewer"] == ("code_reviewer", strongest_chat_model)
    assert captured["checkpointer"] is request.app.state.session_checkpointer


def test_session_graph_supplies_every_production_runtime_adapter(monkeypatch) -> None:
    """Composition supplies recorder, workspace factory, publisher factory, and checkpointer explicitly."""
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_checkpointer=object())))
    coding_run_store = object()
    repository_store = object()
    captured = {}

    monkeypatch.setattr(dependencies, "build_graph", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(dependencies, "CodeGenerator", lambda model: ("code_generator", model))
    monkeypatch.setattr(dependencies, "CodeReviewer", lambda model: ("code_reviewer", model))
    monkeypatch.setattr(dependencies, "CodingRunRecorder", lambda store: ("recorder", store))
    monkeypatch.setattr(dependencies, "build_patch_publisher_factory", lambda store: ("publisher_factory", store))

    dependencies.get_session_graph(
        request=request,
        chat_model=object(),
        strong_chat_model=object(),
        strongest_chat_model=object(),
        document_retriever=object(),
        coding_run_store=coding_run_store,
        repository_store=repository_store,
    )

    assert captured["run_recorder"] == ("recorder", coding_run_store)
    assert captured["workspace_factory"] is dependencies.LocalGitWorkspace
    assert captured["publisher_factory"] == ("publisher_factory", repository_store)
    assert captured["checkpointer"] is request.app.state.session_checkpointer


def test_document_retriever_is_scoped_to_current_user(monkeypatch) -> None:
    """The retriever provider binds retrieval to the authenticated user's tenant."""
    user = SimpleNamespace(id=uuid.uuid4())
    weaviate_resources = object()
    repository_document_store = object()
    reranker = object()
    retriever = object()
    captured = {}

    def fake_retriever(resources, tenant, store, received_reranker):
        captured["retriever_args"] = (resources, tenant, store, received_reranker)
        return retriever

    monkeypatch.setattr(dependencies, "create_reranker", lambda: reranker)
    monkeypatch.setattr(dependencies, "DocumentRetriever", fake_retriever)

    result = dependencies.get_document_retriever(user, weaviate_resources, repository_document_store)

    assert result is retriever
    assert captured["retriever_args"] == (weaviate_resources, str(user.id), repository_document_store, reranker)
