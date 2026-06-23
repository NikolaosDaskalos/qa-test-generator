"""The bounded code generator: structured files + harvested External References.

These drive the generator through an injected fake agent so the loop boundary,
structured-file extraction, and External Reference harvesting are verified without
any real model or network call.
"""

import json
import logging

import httpx
import openai
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.code_generator import CodeGenerator, _GeneratorResponse
from app.schemas import GeneratedFile, ReviewFinding


class FakeAgent:
    """A stand-in compiled agent that records its invocation and returns a final state."""

    def __init__(self, final_state) -> None:
        self.final_state = final_state
        self.invocations = []

    def invoke(self, agent_input, config=None):
        self.invocations.append((agent_input, config))
        return self.final_state


class RaisingAgent:
    """A stand-in agent that always fails with the given provider error."""

    def __init__(self, error) -> None:
        self.error = error

    def invoke(self, agent_input, config=None):
        raise self.error


def _openai_status_error(status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.APIStatusError("boom", response=httpx.Response(status_code, request=request), body=None)


def _web_search_message(results) -> ToolMessage:
    return ToolMessage(content=json.dumps({"results": results}), name="web_search", tool_call_id="c1")


def _build_generator(monkeypatch, final_state):
    """Build a generator whose single agent is a FakeAgent returning ``final_state``.

    The agent is injected by monkeypatching ``create_agent`` so tests drive the
    generator through its public ``generate``/``revise`` interface with no real model.
    """
    agent = FakeAgent(final_state)
    monkeypatch.setattr("app.agents.code_generator.create_agent", lambda *a, **k: agent)
    return CodeGenerator(llm="primary", fallback_llm="fallback"), agent


def test_code_generator_extracts_structured_files_and_harvests_external_references(monkeypatch) -> None:
    """The structured response yields files; web_search tool messages yield External References."""
    final_state = {
        "messages": [
            HumanMessage(content="task"),
            AIMessage(content="searching"),
            _web_search_message([{"url": "https://docs.pytest.org", "title": "pytest"}, {"url": "https://docs.pytest.org", "title": "dup"}]),
            AIMessage(content="done"),
        ],
        "structured_response": _GeneratorResponse(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]),
    }
    generator, _agent = _build_generator(monkeypatch, final_state)

    proposal = generator.generate(task="add tests for auth", source_documents=[], test_documents=[])

    assert [file.path for file in proposal.generated_files] == ["tests/test_auth.py"]
    assert [reference.url for reference in proposal.external_references] == ["https://docs.pytest.org"]


def test_code_generator_falls_over_to_the_fallback_provider_on_a_transient_generation_error(monkeypatch) -> None:
    """A transient primary generator failure re-runs generation on the cross-provider fallback agent."""

    def fake_create_agent(llm, **_kwargs):
        if llm == "primary":
            return RaisingAgent(_openai_status_error(429))
        return FakeAgent(
            {
                "messages": [],
                "structured_response": _GeneratorResponse(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_from_fallback(): ...")]),
            }
        )

    monkeypatch.setattr("app.agents.code_generator.create_agent", fake_create_agent)
    generator = CodeGenerator(llm="primary", fallback_llm="fallback")

    proposal = generator.generate(task="add tests", source_documents=[], test_documents=[])

    assert [file.path for file in proposal.generated_files] == ["tests/test_auth.py"]


def test_code_generator_fails_fast_on_a_deterministic_error_without_the_fallback(monkeypatch) -> None:
    """A deterministic primary failure (400) is not masked by the fallback provider."""
    fallback_invoked = {"count": 0}

    def fake_create_agent(llm, **_kwargs):
        if llm == "primary":
            return RaisingAgent(_openai_status_error(400))

        class _Counting(FakeAgent):
            def invoke(self, agent_input, config=None):
                fallback_invoked["count"] += 1
                return super().invoke(agent_input, config)

        return _Counting({"messages": [], "structured_response": _GeneratorResponse(generated_files=[])})

    monkeypatch.setattr("app.agents.code_generator.create_agent", fake_create_agent)
    generator = CodeGenerator(llm="primary", fallback_llm="fallback")

    try:
        generator.generate(task="add tests", source_documents=[], test_documents=[])
    except openai.APIStatusError:
        pass
    else:
        raise AssertionError("expected the deterministic 400 to propagate")

    assert fallback_invoked["count"] == 0


def test_code_generator_falls_over_to_the_fallback_provider_on_a_transient_revision_error(monkeypatch) -> None:
    """A transient primary generator failure re-runs revision on the cross-provider fallback agent."""

    def fake_create_agent(llm, **_kwargs):
        if llm == "primary":
            return RaisingAgent(_openai_status_error(503))
        return FakeAgent(
            {
                "messages": [_web_search_message([{"url": "https://docs.pytest.org/fixtures", "title": "fixtures"}])],
                "structured_response": _GeneratorResponse(
                    generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_revised_from_fallback(): ...")]
                ),
            }
        )

    monkeypatch.setattr("app.agents.code_generator.create_agent", fake_create_agent)
    generator = CodeGenerator(llm="primary", fallback_llm="fallback")

    proposal = generator.revise(
        task="add tests",
        source_documents=[],
        test_documents=[],
        prior_files=[GeneratedFile(path="tests/test_auth.py", content="def test_old(): ...")],
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        findings=[ReviewFinding(category="coverage", detail="missing edge case")],
    )

    assert [file.path for file in proposal.generated_files] == ["tests/test_auth.py"]
    assert [reference.url for reference in proposal.external_references] == ["https://docs.pytest.org/fixtures"]


def test_code_generator_logs_a_warning_when_the_fallback_fires(monkeypatch, caplog) -> None:
    """A generator fallback warning names the primary model, fallback model, and provider error reason."""

    def fake_create_agent(llm, **_kwargs):
        if llm == "gpt-4o":
            return RaisingAgent(_openai_status_error(500))
        return FakeAgent({"messages": [], "structured_response": _GeneratorResponse(generated_files=[])})

    monkeypatch.setattr("app.agents.code_generator.create_agent", fake_create_agent)
    generator = CodeGenerator(llm="gpt-4o", fallback_llm="claude-sonnet-4-6")

    with caplog.at_level(logging.WARNING):
        generator.generate(task="add tests", source_documents=[], test_documents=[])

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "gpt-4o" in message
    assert "claude-sonnet-4-6" in message
    assert "500" in message


def test_code_generator_caps_the_web_search_loop_with_a_tool_call_limit(monkeypatch) -> None:
    """The agent is built with a per-run tool-call limit that stops the loop gracefully."""
    captured = {}

    def fake_create_agent(_llm, **kwargs):
        captured.update(kwargs)
        return FakeAgent({"messages": [], "structured_response": _GeneratorResponse(generated_files=[])})

    monkeypatch.setattr("app.agents.code_generator.create_agent", fake_create_agent)

    CodeGenerator(llm="primary", fallback_llm="fallback")

    middleware = captured["middleware"]
    assert len(middleware) == 1
    assert middleware[0].run_limit == 3
    assert middleware[0].exit_behavior == "continue"


def test_code_generator_revises_a_prior_proposal_against_reviewer_findings(monkeypatch) -> None:
    """Revision returns the new files and prompts with the prior proposal, the canonical diff, and the findings."""
    final_state = {
        "messages": [],
        "structured_response": _GeneratorResponse(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...\ndef test_y(): ...")]),
    }
    generator, agent = _build_generator(monkeypatch, final_state)

    proposal = generator.revise(
        task="add tests for auth",
        source_documents=[],
        test_documents=[],
        prior_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")],
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        findings=[ReviewFinding(category="coverage", detail="missing unhappy-path test")],
    )

    assert [file.path for file in proposal.generated_files] == ["tests/test_auth.py"]
    agent_input, _config = agent.invocations[0]
    prompt = agent_input["messages"][0].content
    # The revision prompt grounds the model in the rejected proposal, the diff, and the findings to address.
    assert "missing unhappy-path test" in prompt
    assert "diff --git a/tests/test_auth.py" in prompt
    assert "def test_x(): ..." in prompt


def test_code_generator_uses_the_primary_web_search_agent_for_both_generation_and_revision(monkeypatch) -> None:
    """The primary web_search-capable agent serves both generation and revision on the normal path."""
    created = []

    def fake_create_agent(llm, tools=None, **kwargs):
        agent = FakeAgent({"messages": [], "structured_response": _GeneratorResponse(generated_files=[])})
        created.append({"agent": agent, "llm": llm, "tools": tools or [], "system_prompt": kwargs["system_prompt"]})
        return agent

    monkeypatch.setattr("app.agents.code_generator.create_agent", fake_create_agent)

    generator = CodeGenerator(llm="primary", fallback_llm="fallback")
    generator.generate(task="add tests", source_documents=[], test_documents=[])
    generator.revise(task="add tests", source_documents=[], test_documents=[], prior_files=[], diff="", findings=[])

    # Primary and fallback agents are constructed, and the normal path uses the primary for both passes.
    assert [item["llm"] for item in created] == ["primary", "fallback"]
    assert len(created[0]["tools"]) == 1
    assert len(created[0]["agent"].invocations) == 2
    assert created[1]["agent"].invocations == []


def test_code_generator_revision_consults_web_search_and_harvests_references(monkeypatch) -> None:
    """Revision may now call web_search, so its tool messages yield External References."""
    final_state = {
        "messages": [
            AIMessage(content="looking up the current framework API"),
            _web_search_message([{"url": "https://docs.pytest.org/fixtures", "title": "fixtures"}]),
            AIMessage(content="done"),
        ],
        "structured_response": _GeneratorResponse(generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")]),
    }
    generator, _agent = _build_generator(monkeypatch, final_state)

    proposal = generator.revise(
        task="add tests for auth",
        source_documents=[],
        test_documents=[],
        prior_files=[GeneratedFile(path="tests/test_auth.py", content="def test_x(): ...")],
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
        findings=[ReviewFinding(category="versioning", detail="uses a deprecated fixture API")],
    )

    assert [reference.url for reference in proposal.external_references] == ["https://docs.pytest.org/fixtures"]
