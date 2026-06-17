"""The thin adapter mapping LangGraph stream modes onto typed Agent Stream events."""

import uuid

from app.streaming.agent_stream import map_graph_stream
from app.schemas.agent_stream import RunStarted, Stage, Token


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


def test_stage_accepts_classifying_and_planning() -> None:
    assert Stage(stage="classifying").stage == "classifying"
    assert Stage(stage="planning").stage == "planning"


def test_custom_events_pass_through_and_messages_become_tokens_in_order() -> None:
    run_id = uuid.uuid4()
    items = [
        ("custom", Stage(stage="classifying")),
        ("custom", RunStarted(coding_run_id=run_id)),
        ("custom", Stage(stage="planning")),
        ("custom", Stage(stage="retrieving")),
        ("custom", Stage(stage="generating")),
        ("messages", (_Message("the "), {"langgraph_node": "generate"})),
        ("messages", (_Message(""), {"langgraph_node": "generate"})),
        ("messages", (_Message("answer"), {"langgraph_node": "generate"})),
    ]

    events = list(map_graph_stream(items))

    assert events == [
        Stage(stage="classifying"),
        RunStarted(coding_run_id=run_id),
        Stage(stage="planning"),
        Stage(stage="retrieving"),
        Stage(stage="generating"),
        Token(content="the "),
        Token(content="answer"),
    ]


def test_message_chunks_from_non_answer_nodes_are_not_streamed_as_tokens() -> None:
    items = [
        ("messages", (_Message('{"intent":'), {"langgraph_node": "classify"})),
        ("messages", (_Message("visible answer"), {"langgraph_node": "generate"})),
        ("messages", (_Message('{"plan":'), {"langgraph_node": "plan"})),
        ("messages", (_Message("metadata missing"), {})),
    ]

    events = list(map_graph_stream(items))

    assert events == [Token(content="visible answer")]
