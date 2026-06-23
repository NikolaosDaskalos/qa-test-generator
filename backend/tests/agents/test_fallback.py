"""The cross-provider fallback foundation: transient classification and agent fallback.

These drive the shared transient-error predicate and the agent-level fallback
wrapper without any live provider call — provider errors are constructed from the
SDK exception types and fakes stand in for the compiled agents.
"""

import logging

import anthropic
import httpx
import openai
import pytest

from app.agents.fallback import is_transient_llm_error, with_agent_fallback


class _Agent:
    """A stand-in compiled agent that returns a final state or raises a provider error."""

    def __init__(self, *, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def invoke(self, agent_input, config=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _anthropic_status_error(status_code: int) -> anthropic.APIStatusError:
    """Build a real Anthropic APIStatusError carrying the given HTTP status."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code, request=request)
    return anthropic.APIStatusError("boom", response=response, body=None)


def test_anthropic_529_overloaded_is_transient() -> None:
    """A 529 overloaded error — surfaced as the base APIStatusError, not a 5xx subclass — is fall-back-worthy."""
    assert is_transient_llm_error(_anthropic_status_error(529)) is True


def test_rate_limit_and_server_errors_are_transient() -> None:
    """429 rate-limit and 5xx server errors are availability blips the other provider may survive."""
    assert is_transient_llm_error(_anthropic_status_error(429)) is True
    assert is_transient_llm_error(_anthropic_status_error(503)) is True


def test_deterministic_4xx_errors_fail_fast() -> None:
    """Bad-request, auth, and context-length errors (all 4xx) are deterministic and must not hop providers."""
    assert is_transient_llm_error(_anthropic_status_error(400)) is False
    assert is_transient_llm_error(_anthropic_status_error(401)) is False
    assert is_transient_llm_error(_anthropic_status_error(422)) is False


def test_timeouts_and_connection_failures_are_transient() -> None:
    """Network timeouts and connection failures carry no status code but are clearly transient."""
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    assert is_transient_llm_error(openai.APITimeoutError(request=request)) is True
    assert is_transient_llm_error(openai.APIConnectionError(request=request)) is True


def test_an_arbitrary_non_provider_error_is_not_transient() -> None:
    """An error with no transient status and no connection type fails fast rather than masking a real bug."""
    assert is_transient_llm_error(ValueError("malformed prompt")) is False


def test_with_agent_fallback_falls_over_on_a_transient_primary_error(caplog) -> None:
    """A transient primary failure (529) re-runs the agent on the cross-provider fallback, returning its result."""
    primary = _Agent(error=_anthropic_status_error(529))
    fallback = _Agent(result={"structured_response": "from-fallback"})
    agent = with_agent_fallback(primary, fallback, primary_label="claude-haiku-4-5", fallback_label="gpt-4o-mini")

    with caplog.at_level(logging.WARNING):
        result = agent.invoke({"messages": []})

    assert result == {"structured_response": "from-fallback"}
    assert fallback.calls == 1


def test_with_agent_fallback_logs_a_warning_naming_primary_fallback_and_reason(caplog) -> None:
    """When the fallback fires it logs a WARNING identifying the primary, the fallback, and why it switched."""
    primary = _Agent(error=_anthropic_status_error(529))
    fallback = _Agent(result={"structured_response": "from-fallback"})
    agent = with_agent_fallback(primary, fallback, primary_label="claude-haiku-4-5", fallback_label="gpt-4o-mini")

    with caplog.at_level(logging.WARNING):
        agent.invoke({"messages": []})

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "claude-haiku-4-5" in message
    assert "gpt-4o-mini" in message
    assert "529" in message


def test_with_agent_fallback_fails_fast_on_a_deterministic_primary_error() -> None:
    """A deterministic primary failure (400) propagates as itself and never invokes the fallback provider."""
    primary = _Agent(error=_anthropic_status_error(400))
    fallback = _Agent(result={"structured_response": "from-fallback"})
    agent = with_agent_fallback(primary, fallback, primary_label="claude-haiku-4-5", fallback_label="gpt-4o-mini")

    with pytest.raises(anthropic.APIStatusError):
        agent.invoke({"messages": []})

    assert fallback.calls == 0
