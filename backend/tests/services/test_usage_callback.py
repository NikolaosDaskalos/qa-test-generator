"""Test the per-turn usage-capturing callback that buffers priced LLM-call records (ADR-0013)."""

from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.services.usage.callback import UsageCapturingCallback
from app.services.usage.pricing import price_for


def _llm_result(message: AIMessage) -> LLMResult:
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _run_call(callback: UsageCapturingCallback, *, node: str, message: AIMessage) -> None:
    run_id = uuid4()
    callback.on_chat_model_start({}, [], run_id=run_id, metadata={"langgraph_node": node})
    callback.on_llm_end(_llm_result(message), run_id=run_id)


def test_callback_buffers_a_priced_record_per_llm_call() -> None:
    """One on_llm_end yields one record with the response's tokens, model, provider, node, and derived cost."""
    callback = UsageCapturingCallback()
    message = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        response_metadata={"model_name": "gpt-4o-mini-2024-07-18"},
    )

    _run_call(callback, node="simple_rag", message=message)

    assert len(callback.records) == 1
    record = callback.records[0]
    assert record.model == "gpt-4o-mini-2024-07-18"
    assert record.provider == "openai"
    assert record.node_name == "simple_rag"
    assert record.input_tokens == 1000
    assert record.output_tokens == 500
    assert record.total_tokens == 1500
    assert record.cost == pytest.approx(price_for("gpt-4o-mini", 1000, 500))


def test_callback_prices_a_fallback_served_call_as_the_model_that_answered() -> None:
    """When the cross-provider fallback answers, the record keys off the response's model, not the primary."""
    callback = UsageCapturingCallback()
    # The default tier's primary is gpt-4o-mini (OpenAI); a transient failure served this
    # call on the Anthropic fallback, so the response reports claude-haiku-4-5.
    message = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500},
        response_metadata={"model": "claude-haiku-4-5"},
    )

    _run_call(callback, node="simple_rag", message=message)

    record = callback.records[0]
    assert record.model == "claude-haiku-4-5"
    assert record.provider == "anthropic"
    assert record.cost == pytest.approx(price_for("claude-haiku-4-5", 1000, 500))
