"""Construct the Tavily web-search client used for External References.

The concrete search client lives here; the LangChain ``web_search`` tool that
wraps it stays under ``agents``.
"""

import os

from langchain_tavily import TavilySearch

from app.core import settings

if settings.TAVILY_API_KEY:
    os.environ["TAVILY_API_KEY"] = settings.TAVILY_API_KEY


def create_web_search_client() -> TavilySearch:
    """Build the Tavily client scoped to test-framework lookups."""
    return TavilySearch(max_results=3, topic="general", include_answer=True, include_raw_content=False, include_images=False)
