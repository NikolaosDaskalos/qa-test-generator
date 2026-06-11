import json
import logging
import os
from typing import Any

from langchain_core.tools import tool
from langchain_tavily import TavilySearch

from app.core.config import settings

logger = logging.getLogger(__name__)


if settings.TAVILY_API_KEY:
    os.environ["TAVILY_API_KEY"] = settings.TAVILY_API_KEY


_tavily_search = TavilySearch(max_results=3, topic="general", include_answer=True, include_raw_content=False, include_images=False)


@tool
def web_search(query: str) -> str:
    """
    Search the web using Tavily and return JSON-serialized results.
    Use this when fresh or external information is needed.
    """

    if not query or not query.strip():
        logger.warning("Web search rejected because the query is empty")
        return json.dumps({"error": "No query provided"}, ensure_ascii=False)
    try:
        logger.info("Web search started query_length=%s", len(query.strip()))
        result: Any = _tavily_search.invoke({"query": query})
        result_count = len(result) if isinstance(result, list | dict) else None
        logger.info("Web search completed result_count=%s", result_count)
        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.error("Web search failed: %s", exc)
        return json.dumps({"error": "Tavily search failed", "details": str(exc)}, ensure_ascii=False)
