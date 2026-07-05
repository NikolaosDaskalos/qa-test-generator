"""A per-turn LangChain callback that captures priced AI Cost records for each LLM call.

Attached via ``config["callbacks"]`` at the graph stream sites, it reads the
provider-reported ``usage_metadata`` off every node's LLM response — uniform across both
providers and the cross-provider fallback wrapper — prices each call through
:func:`price_for`, and buffers a :class:`CapturedUsage` per call. The buffer is a pure
in-memory ledger with no store dependency: the session service stamps the records with
the turn's attribution and persists them once the answering turn is known.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.services.usage.pricing import price_for


@dataclass(frozen=True)
class CapturedUsage:
    """One metered LLM call: the response's model/provider, its node, tokens, and derived cost."""

    model: str
    provider: str
    node_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float | None


class UsageCapturingCallback(BaseCallbackHandler):
    """Buffer one priced usage record per LLM call over the course of a single turn."""

    def __init__(self) -> None:
        self.records: list[CapturedUsage] = []
        # The originating graph node per in-flight run, learned at start and consumed at end.
        self._nodes: dict[UUID, str] = {}

    def on_chat_model_start(self, serialized: Any, messages: Any, *, run_id: UUID, metadata: dict | None = None, **kwargs: Any) -> None:
        """Remember which graph node issued this call so its usage can be attributed on end."""
        self._nodes[run_id] = (metadata or {}).get("langgraph_node", "")

    def on_llm_start(self, serialized: Any, prompts: Any, *, run_id: UUID, metadata: dict | None = None, **kwargs: Any) -> None:
        """Same attribution for plain-LLM (non-chat) call sites."""
        self._nodes[run_id] = (metadata or {}).get("langgraph_node", "")

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        """Buffer a priced record from the response's reported model and token usage."""
        message = self._response_message(response)
        if message is None:
            self._nodes.pop(run_id, None)
            return
        usage = getattr(message, "usage_metadata", None) or {}
        model = self._response_model(message)
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))
        self.records.append(
            CapturedUsage(
                model=model,
                provider=_provider_for(model),
                node_name=self._nodes.pop(run_id, ""),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=price_for(model, input_tokens, output_tokens),
            )
        )

    @staticmethod
    def _response_message(response: LLMResult) -> Any | None:
        """Return the first generation's message, or ``None`` for an empty result."""
        for generation_list in response.generations:
            for generation in generation_list:
                message = getattr(generation, "message", None)
                if message is not None:
                    return message
        return None

    @staticmethod
    def _response_model(message: Any) -> str:
        """Read the model the response reports (OpenAI ``model_name`` / Anthropic ``model``)."""
        metadata = getattr(message, "response_metadata", None) or {}
        for key in ("model_name", "model"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return ""


def _provider_for(model: str) -> str:
    """Derive the serving provider from the response's model id."""
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gpt"):
        return "openai"
    return ""
