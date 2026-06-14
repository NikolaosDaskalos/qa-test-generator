"""Test repository-scoped retrieval in answer chains."""

import uuid

from app.core.config import settings
from app.models.source_document import SourceDocument
from app.rag import chain_builder
from app.rag.chain_builder import INSUFFICIENT_EVIDENCE_ANSWER, ChainBuilder
from app.schemas.agent_stream import Answer, Citation, Stage, Token


class FakeRunnable:
    """Provide the minimal prompt, model, and parser pipeline behavior."""

    stream_values = []
    output_tokens = ["answer"]

    def __or__(self, other):
        return self

    def invoke(self, values):
        return "reformulated question"

    def stream(self, values):
        self.stream_values.append(values)
        yield from self.output_tokens


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


def test_answer_stream_scopes_retrieval_to_repository(monkeypatch) -> None:
    """Forward repository identity and hybrid alpha in retrieval."""
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

    events = list(builder.answer_stream("question", repository_id=repository_id))

    assert retriever.calls == [
        (
            "question",
            {
                "repository_id": repository_id,
                "k": settings.TOP_K,
                "alpha": settings.HYBRID_SEARCH_ALPHA,
                "parent_limit": settings.FINAL_PARENT_LIMIT,
            },
        )
    ]
    assert FakeRunnable.stream_values[-1]["context"] == "[Source: backend/app/parent.py]\ncomplete parent content"
    # The chain owns the ordered turn: stage progress, tokens, then a terminal Answer with citations.
    assert events == [
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content="answer"),
        Answer(text="answer", citations=[Citation(source="backend/app/parent.py")]),
    ]


def test_answer_stream_deduplicates_citations_in_retrieval_order(monkeypatch) -> None:
    """Repeated source paths collapse to one ordered citation per file."""
    monkeypatch.setattr(chain_builder, "ChatPromptTemplate", FakePromptTemplate)
    FakeRunnable.stream_values = []
    repository_id = uuid.uuid4()
    evidence = [
        SourceDocument(repository_id=repository_id, content="a", doc_metadata={"source": "app/auth.py"}),
        SourceDocument(repository_id=repository_id, content="b", doc_metadata={"source": "app/auth.py"}),
        SourceDocument(repository_id=repository_id, content="c", doc_metadata={"source": "app/login.py"}),
    ]
    builder = ChainBuilder(object(), RecordingRetriever(evidence))

    events = list(builder.answer_stream("question", repository_id=repository_id))

    terminal = events[-1]
    assert isinstance(terminal, Answer)
    assert terminal.citations == [Citation(source="app/auth.py"), Citation(source="app/login.py")]


def test_answer_stream_skips_empty_model_chunks(monkeypatch) -> None:
    """Metadata-only model chunks do not become empty Token events."""
    monkeypatch.setattr(chain_builder, "ChatPromptTemplate", FakePromptTemplate)
    monkeypatch.setattr(FakeRunnable, "output_tokens", ["", "answer", "", " complete"])
    repository_id = uuid.uuid4()
    evidence = [
        SourceDocument(repository_id=repository_id, content="evidence", doc_metadata={"source": "app/example.py"}),
    ]
    builder = ChainBuilder(object(), RecordingRetriever(evidence))

    events = list(builder.answer_stream("question", repository_id=repository_id))

    assert [event.content for event in events if isinstance(event, Token)] == ["answer", " complete"]
    assert events[-1] == Answer(text="answer complete", citations=[Citation(source="app/example.py")])


def test_answer_stream_returns_insufficient_evidence_without_calling_the_model(monkeypatch) -> None:
    """Empty Repository Evidence yields a deterministic answer and no generation."""
    monkeypatch.setattr(chain_builder, "ChatPromptTemplate", FakePromptTemplate)
    FakeRunnable.stream_values = []
    repository_id = uuid.uuid4()
    retriever = RecordingRetriever([])  # no Repository Evidence retrieved
    builder = ChainBuilder(object(), retriever)

    events = list(builder.answer_stream("question", repository_id=repository_id))

    # Retrieval is still attempted and scoped to the Repository.
    assert retriever.calls[-1][1]["repository_id"] == repository_id
    # The language model is never streamed for generation.
    assert FakeRunnable.stream_values == []
    # An explicit insufficient-evidence answer is the only emitted content, with no citations.
    assert events == [
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content=INSUFFICIENT_EVIDENCE_ANSWER),
        Answer(text=INSUFFICIENT_EVIDENCE_ANSWER, citations=[]),
    ]
