"""Shared agent middleware construction.

Both the generator and the reviewer bound their single-tool ReAct loop with the
same per-run tool-call limit, so the configuration lives here rather than being
duplicated in each agent.
"""

from langchain.agents.middleware import ToolCallLimitMiddleware

from app.agent.agents.tools import web_search

# Max ``web_search`` calls allowed per single ``invoke()`` run.
TOOL_CALL_RUN_LIMIT = 3


def build_tool_call_limit_middleware() -> ToolCallLimitMiddleware:
    """Cap ``web_search`` calls per run without abruptly stopping the agent.

    The limit is scoped to ``web_search`` by ``tool_name``. It must not be a
    global tool-call cap: when ``response_format`` resolves to a tool strategy,
    the agent delivers its structured response as a tool call, and an unscoped
    limit would block *that* call once the web-search budget is spent — dropping
    the structured response and yielding an empty proposal.

    ``exit_behavior="continue"`` blocks further ``web_search`` calls once the
    limit is hit but lets the model finish and still return its structured
    response — never a mid-flight stop that would drop that response.
    """
    return ToolCallLimitMiddleware(
        tool_name=web_search.name,
        run_limit=TOOL_CALL_RUN_LIMIT,
        exit_behavior="continue",
    )
