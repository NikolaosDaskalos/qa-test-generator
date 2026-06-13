"""Test repository-scoped retrieval in standard and HyDE answer chains."""

import uuid

import pytest

from app.core.config import settings
from app.rag import chain_builder
from app.rag.chain_builder import ChainBuilder


class FakeRunnable:
    """Provide the minimal prompt, model, and parser pipeline behavior."""

    def __or__(self, other):
        return self

    def invoke(self, values):
        return "hypothetical document"

    def stream(self, values):
        yield "answer"


class FakePromptTemplate:
    """Build deterministic fake LCEL runnables."""

    @staticmethod
    def from_messages(messages):
        return FakeRunnable()

    @staticmethod
    def from_template(template):
        return FakeRunnable()


class RecordingRetriever:
    """Record retrieval arguments for contract assertions."""

    def __init__(self) -> None:
        self.calls = []

    def search_with_scores(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return []


@pytest.mark.parametrize(("use_hyde", "expected_query"), [(False, "question"), (True, "hypothetical document")])
def test_answer_stream_scopes_retrieval_to_repository(monkeypatch, use_hyde, expected_query) -> None:
    """Forward repository identity and hybrid alpha in both retrieval modes."""
    monkeypatch.setattr(chain_builder, "ChatPromptTemplate", FakePromptTemplate)
    repository_id = uuid.uuid4()
    retriever = RecordingRetriever()
    builder = ChainBuilder(object(), retriever)

    events = list(builder.answer_stream("question", repository_id=repository_id, use_hyde=use_hyde))

    assert retriever.calls == [(expected_query, {"repository_id": repository_id, "k": settings.TOP_K, "alpha": settings.HYBRID_SEARCH_ALPHA})]
    assert events[-1]["type"] == "done"
