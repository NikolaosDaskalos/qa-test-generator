"""Test the concrete LLM and reranker client construction."""

from app.core import settings
from app.integrations import llm


def test_reranker_is_configured_from_settings(monkeypatch) -> None:
    """The reranker is built with the configured model and top-k cutoff."""
    captured = {}

    def fake_cohere(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm, "CohereRerank", fake_cohere)

    llm.create_reranker()

    assert captured["model"] == settings.COHERE_RERANK_MODEL
    assert captured["top_n"] == settings.TOP_K


def test_chat_model_uses_streaming_and_requested_limits(monkeypatch) -> None:
    """The OpenAI chat model is built streaming with the requested model and token cap."""
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm, "ChatOpenAI", fake_openai)

    llm.create_chat_model("gpt-test", 123)

    assert captured["model"] == "gpt-test"
    assert captured["max_tokens"] == 123
    assert captured["streaming"] is True
