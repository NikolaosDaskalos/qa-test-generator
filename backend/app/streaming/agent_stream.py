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


# The tag every strategy node attaches to its single grounded final-answer stream, so its
# token chunks — and only those — become ``Token`` events. A strategy node also makes
# node-local model calls that must never reach the client (multi-query variant generation,
# decomposition, and the sub-answers the decompose nodes batch/invoke): those run under the
# same ``langgraph_node`` name, so attribution by node alone would leak them. Tagging the
# final-answer stream and filtering on the tag attributes tokens to the answer, not the node.
FINAL_ANSWER_TAG = "final_answer"


def map_graph_stream(stream_items: Iterable[tuple[str, object]]) -> Iterator[AgentStreamEvent]:
    """Fold ``(mode, chunk)`` items onto typed events, preserving order.

    ``custom`` chunks are already typed markers and pass straight through;
    ``messages`` chunks are ``(message, metadata)`` pairs, and only those carrying
    ``FINAL_ANSWER_TAG`` (the strategy node's final-answer stream) turn their non-empty
    content into a ``Token`` — node-local variant/decomposition/sub-answer calls are untagged
    and so never leak.
    """
    for mode, chunk in stream_items:
        if mode == "custom":
            yield chunk  # type: ignore[misc]
        elif mode == "messages":
            message, metadata = chunk  # type: ignore[misc]
            if not isinstance(metadata, dict) or FINAL_ANSWER_TAG not in (metadata.get("tags") or []):
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
