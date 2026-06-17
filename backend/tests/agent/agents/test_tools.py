"""The bounded web_search tool: researching progress and result passthrough."""

import json
from types import SimpleNamespace

from app.agent.agents import tools
from app.schemas.agent_stream import Stage


def test_web_search_emits_researching_and_returns_results(monkeypatch) -> None:
    """A real query streams a researching marker and returns the search results."""
    emitted = []
    monkeypatch.setattr(tools, "emit", emitted.append)
    monkeypatch.setattr(tools, "_tavily_search", SimpleNamespace(invoke=lambda payload: {"results": [{"url": "https://docs.pytest.org", "title": "pytest"}]}))

    output = tools.web_search.invoke({"query": "pytest fixtures best practices"})

    assert any(isinstance(event, Stage) and event.stage == "researching" for event in emitted)
    assert "docs.pytest.org" in output


def test_web_search_rejects_an_empty_query_without_researching(monkeypatch) -> None:
    """An empty query is rejected before any researching marker or search call."""
    emitted = []
    monkeypatch.setattr(tools, "emit", emitted.append)

    output = tools.web_search.invoke({"query": "   "})

    assert emitted == []
    assert json.loads(output) == {"error": "No query provided"}
