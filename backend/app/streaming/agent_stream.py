"""Bridge between LangGraph's stream modes and the typed Agent Stream.

Graph nodes emit ordered stage and run markers on the ``custom`` stream while a
generating node's token chunks ride the ``messages`` stream. ``emit`` is the only
way nodes publish a custom marker; ``map_graph_stream`` is the only adapter that
folds both modes back onto the typed ``AgentStreamEvent`` union.

Code-generation terminal domain events are emitted by the graph node that
produces them and are forwarded like any other custom marker. This supersedes
ADR-0002's earlier "caller decides from final state" stream contract. Repository
question ``Result`` events remain assembled by the session service after
persistence because they need the stored assistant message id.
"""

import json
import logging
from collections.abc import Iterable, Iterator

from app.schemas import AgentStreamEvent, Token

logger = logging.getLogger(__name__)

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


# The repository-question strategy nodes whose grounded-answer token stream becomes
# ``Token`` events. Each Question Shape strategy owns its own final-answer streaming, so
# tokens are attributed by strategy-node name (the analyzing/variant structured calls do
# not stream and so never reach here).
_ANSWER_GENERATION_NODES = frozenset({"simple_rag", "decompose_parallel", "decompose_recursive"})


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
            if not isinstance(metadata, dict) or metadata.get("langgraph_node") not in _ANSWER_GENERATION_NODES:
                continue
            content = getattr(message, "content", "") or ""
            if content:
                yield Token(content=content)


def to_sse_frames(events: Iterable[AgentStreamEvent]) -> Iterator[str]:
    """Serialize typed Agent Stream events as server-sent event frames.

    This is the only place that knows the SSE wire format. The terminal ``Result``
    event closes a successful stream — there is no separate ``done`` frame. An
    unexpected mid-stream failure surfaces as a single out-of-band ``error`` frame
    (outside the typed vocabulary) rather than tearing down the connection.
    """
    try:
        for event in events:
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception:
        logger.exception("Streaming answer failed")
        error = {"type": "error", "message": "An error occurred while generating the answer."}
        yield f"data: {json.dumps(error)}\n\n"
