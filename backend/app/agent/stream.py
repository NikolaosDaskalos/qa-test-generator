"""Bridge between LangGraph's stream modes and the typed Agent Stream.

Graph nodes emit ordered stage and run markers on the ``custom`` stream while a
generating node's token chunks ride the ``messages`` stream. ``emit`` is the only
way nodes publish a custom marker; ``map_graph_stream`` is the only adapter that
folds both modes back onto the typed ``AgentStreamEvent`` union. Terminal domain
events (``Result``, ``RunFailure``) are decided by the caller from final state.
"""

from collections.abc import Iterable, Iterator

from app.schemas.agent_stream import AgentStreamEvent, Token

try:  # pragma: no cover - import guard for environments without the helper
    from langgraph.config import get_stream_writer
except ImportError:  # pragma: no cover
    get_stream_writer = None  # type: ignore[assignment]


def emit(event: AgentStreamEvent) -> None:
    """Publish a typed marker on the custom stream; a no-op outside streaming."""
    if get_stream_writer is None:
        return
    try:
        writer = get_stream_writer()
    except Exception:
        return
    if writer is not None:
        writer(event)


_ANSWER_GENERATION_NODE = "generate"


def map_graph_stream(stream_items: Iterable[tuple[str, object]]) -> Iterator[AgentStreamEvent]:
    """Fold ``(mode, chunk)`` items onto typed events, preserving order.

    ``custom`` chunks are already typed markers and pass straight through;
    answer-generation ``messages`` chunks are ``(message, metadata)`` pairs
    whose non-empty content becomes a ``Token``.
    """
    for mode, chunk in stream_items:
        if mode == "custom":
            yield chunk  # type: ignore[misc]
        elif mode == "messages":
            message, metadata = chunk  # type: ignore[misc]
            if not isinstance(metadata, dict) or metadata.get("langgraph_node") != _ANSWER_GENERATION_NODE:
                continue
            content = getattr(message, "content", "") or ""
            if content:
                yield Token(content=content)
