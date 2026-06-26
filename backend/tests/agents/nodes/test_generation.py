"""The shared grounded-answer helper that every Question Shape strategy streams through."""

from types import SimpleNamespace

from app.agents.nodes.generation import generate_grounded_answer, stream_and_cite
from app.streaming import FINAL_ANSWER_TAG


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _RecordingLLM:
    """Records the config of every ``stream`` call so tag propagation can be asserted."""

    def __init__(self, *, tokens=("answer",)) -> None:
        self._tokens = tokens
        self.stream_configs: list = []

    def stream(self, messages, config=None):
        self.stream_configs.append(config)
        for token in self._tokens:
            yield _Chunk(token)


def _document(source: str) -> SimpleNamespace:
    return SimpleNamespace(doc_metadata={"source": source}, content=f"contents of {source}")


def test_stream_and_cite_tags_the_final_answer_stream() -> None:
    """The final-answer stream carries FINAL_ANSWER_TAG so only it — not node-local sub-answer calls — becomes Tokens."""
    llm = _RecordingLLM()

    stream_and_cite(llm, messages=[], documents=[_document("a.py")])

    tags = [tag for config in llm.stream_configs for tag in (config or {}).get("tags", [])]
    assert FINAL_ANSWER_TAG in tags


def test_generate_grounded_answer_tags_the_final_answer_stream() -> None:
    """The single-answer path (simple_rag) tags its stream the same way as the decompose synthesis."""
    llm = _RecordingLLM()

    generate_grounded_answer(llm, question="what calls login", documents=[_document("auth.py")])

    tags = [tag for config in llm.stream_configs for tag in (config or {}).get("tags", [])]
    assert FINAL_ANSWER_TAG in tags
