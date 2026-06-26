"""The thin adapter mapping LangGraph stream modes onto typed Agent Stream events."""

import typing
import uuid

from app.schemas import AgentStreamEvent, PatchResult, RunStarted, Stage, Token
from app.streaming import map_graph_stream, to_sse_frames


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


def test_patch_result_is_not_a_member_of_the_agent_stream_union() -> None:
    """PatchResult is internal graph state, never on the wire, so it is absent from the typed Agent Stream union."""
    assert PatchResult not in typing.get_args(AgentStreamEvent)


def test_stage_accepts_classifying_and_planning() -> None:
    assert Stage(stage="classifying").stage == "classifying"
    assert Stage(stage="planning").stage == "planning"


def test_custom_events_pass_through_and_messages_become_tokens_in_order() -> None:
    run_id = uuid.uuid4()
    items = [
        ("custom", Stage(stage="classifying")),
        ("custom", RunStarted(coding_run_id=run_id)),
        ("custom", Stage(stage="planning")),
        ("custom", Stage(stage="analyzing")),
        ("custom", Stage(stage="retrieving")),
        ("custom", Stage(stage="generating")),
        ("messages", (_Message("the "), {"langgraph_node": "simple_rag"})),
        ("messages", (_Message(""), {"langgraph_node": "simple_rag"})),
        ("messages", (_Message("answer"), {"langgraph_node": "simple_rag"})),
    ]

    events = list(map_graph_stream(items))

    assert events == [
        Stage(stage="classifying"),
        RunStarted(coding_run_id=run_id),
        Stage(stage="planning"),
        Stage(stage="analyzing"),
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content="the "),
        Token(content="answer"),
    ]


def test_message_chunks_from_non_answer_nodes_are_not_streamed_as_tokens() -> None:
    items = [
        ("messages", (_Message('{"intent":'), {"langgraph_node": "classify"})),
        ("messages", (_Message("visible answer"), {"langgraph_node": "simple_rag"})),
        ("messages", (_Message('{"plan":'), {"langgraph_node": "plan"})),
        ("messages", (_Message("metadata missing"), {})),
    ]

    events = list(map_graph_stream(items))

    assert events == [Token(content="visible answer")]


def test_decompose_parallel_synthesis_chunks_become_tokens() -> None:
    """The decompose_parallel node's synthesized answer streams as Tokens, just like simple_rag."""
    items = [
        ("custom", Stage(stage="decomposing")),
        ("custom", Stage(stage="synthesizing")),
        ("messages", (_Message("final "), {"langgraph_node": "decompose_parallel"})),
        ("messages", (_Message("answer"), {"langgraph_node": "decompose_parallel"})),
    ]

    events = list(map_graph_stream(items))

    assert events == [Stage(stage="decomposing"), Stage(stage="synthesizing"), Token(content="final "), Token(content="answer")]


def test_decompose_recursive_synthesis_chunks_become_tokens() -> None:
    """The decompose_recursive node's synthesized answer streams as Tokens for chained questions."""
    items = [
        ("custom", Stage(stage="decomposing")),
        ("custom", Stage(stage="synthesizing")),
        ("messages", (_Message("recursive "), {"langgraph_node": "decompose_recursive"})),
        ("messages", (_Message("answer"), {"langgraph_node": "decompose_recursive"})),
    ]

    events = list(map_graph_stream(items))

    assert events == [
        Stage(stage="decomposing"),
        Stage(stage="synthesizing"),
        Token(content="recursive "),
        Token(content="answer"),
    ]


def test_to_sse_frames_serializes_typed_events_as_server_sent_frames() -> None:
    run_id = uuid.uuid4()
    events = [Stage(stage="planning"), RunStarted(coding_run_id=run_id)]

    frames = list(to_sse_frames(events))

    assert frames == [f"data: {event.model_dump_json()}\n\n" for event in events]


def test_to_sse_frames_emits_out_of_band_error_frame_when_streaming_fails() -> None:
    def _failing() -> typing.Iterator[AgentStreamEvent]:
        yield Stage(stage="planning")
        raise RuntimeError("boom")

    frames = list(to_sse_frames(_failing()))

    assert frames[0] == f"data: {Stage(stage='planning').model_dump_json()}\n\n"
    assert frames[1] == 'data: {"type": "error", "message": "An error occurred while generating the answer."}\n\n'
