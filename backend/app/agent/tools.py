import json
import logging
import os
from typing import Any

from langchain_core.tools import tool
from langchain_tavily import TavilySearch

from app.agent.stream import emit
from app.core.config import settings
from app.schemas.agent_stream import Stage

logger = logging.getLogger(__name__)


if settings.TAVILY_API_KEY:
    os.environ["TAVILY_API_KEY"] = settings.TAVILY_API_KEY


_tavily_search = TavilySearch(max_results=3, topic="general", include_answer=True, include_raw_content=False, include_images=False)


@tool
def web_search(query: str) -> str:
    """Look up a test framework's current syntax and best practices on the web.

    Use this ONLY to confirm how to write tests — e.g. a testing library's current
    API, fixtures, assertion style, mocking patterns, or idioms (pytest, unittest,
    etc.). Good queries name the framework and the technique, like
    "pytest parametrize fixtures example" or "unittest mock patch async".

    Do NOT use it to learn anything about the repository under test: its modules,
    functions, behavior, or file layout come only from the provided Repository
    Evidence, never from the web. Results are external references about test-writing
    technique and must not ground claims about the repository's own code.

    Returns JSON-serialized search results.
    """

    if not query or not query.strip():
        logger.warning("Web search rejected because the query is empty")
        return json.dumps({"error": "No query provided"}, ensure_ascii=False)
    emit(Stage(stage="researching"))
    try:
        logger.info("Web search started query_length=%s", len(query.strip()))
        result: Any = _tavily_search.invoke({"query": query})
        result_count = len(result) if isinstance(result, list | dict) else None
        logger.info("Web search completed result_count=%s", result_count)
        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.error("Web search failed: %s", exc)
        return json.dumps({"error": "Tavily search failed", "details": str(exc)}, ensure_ascii=False)
