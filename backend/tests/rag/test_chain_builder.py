"""Test repository-scoped retrieval in standard and HyDE answer chains."""

import uuid

import pytest

from app.core.config import settings
from app.models.source_document import SourceDocument
from app.rag import chain_builder
from app.rag.chain_builder import ChainBuilder


class FakeRunnable:
    """Provide the minimal prompt, model, and parser pipeline behavior."""

    stream_values = []

    def __or__(self, other):
        return self

    def invoke(self, values):
        return "hypothetical document"

    def stream(self, values):
        self.stream_values.append(values)
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

    def __init__(self, evidence=None) -> None:
        self.calls = []
        self.evidence = evidence or []

    def retrieve_evidence(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.evidence


@pytest.mark.parametrize(("use_hyde", "expected_query"), [(False, "question"), (True, "hypothetical document")])
def test_answer_stream_scopes_retrieval_to_repository(monkeypatch, use_hyde, expected_query) -> None:
    """Forward repository identity and hybrid alpha in both retrieval modes."""
    monkeypatch.setattr(chain_builder, "ChatPromptTemplate", FakePromptTemplate)
    FakeRunnable.stream_values = []
    repository_id = uuid.uuid4()
    parent = SourceDocument(
        repository_id=repository_id,
        content="complete parent content",
        doc_metadata={"source": "backend/app/parent.py", "page": "parent-page"},
    )
    retriever = RecordingRetriever([parent])
    builder = ChainBuilder(object(), retriever)

    events = list(builder.answer_stream("question", repository_id=repository_id, use_hyde=use_hyde))

    assert retriever.calls == [
        (
            expected_query,
            {
                "repository_id": repository_id,
                "k": settings.TOP_K,
                "alpha": settings.HYBRID_SEARCH_ALPHA,
                "parent_limit": settings.FINAL_PARENT_LIMIT,
            },
        )
    ]
    assert FakeRunnable.stream_values[-1]["context"] == "[Source: backend/app/parent.py]\ncomplete parent content"
    assert events[-1]["type"] == "done"
    assert events[-1]["sources"] == [
        {
            "source": "backend/app/parent.py",
            "page": "parent-page",
            "chunk": "complete parent content",
            "score": None,
        }
    ]
