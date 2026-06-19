"""The bounded ReAct test generator: structured files + harvested External References.

These drive the generator through an injected fake agent so the loop boundary,
structured-file extraction, and External Reference harvesting are verified without
any real model or network call.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.agents.generator import ReActTestGenerator, _GeneratorResponse
from app.schemas import GeneratedFile, ReviewFinding


class FakeAgent:
    """A stand-in compiled agent that records its invocation and returns a final state."""

    def __init__(self, final_state) -> None:
        self.final_state = final_state
        self.invocations = []

    def invoke(self, agent_input, config=None):
        self.invocations.append((agent_input, config))
        return self.final_state


def _web_search_message(results) -> ToolMessage:
    return ToolMessage(content=json.dumps({"results": results}), name="web_search", tool_call_id="c1")


def _build_generator(monkeypatch, final_state):
    """Build a generator whose single agent is a FakeAgent returning ``final_state``.

    The agent is injected by monkeypatching ``create_agent`` so tests drive the
    generator through its public ``generate``/``revise`` interface with no real model.
    """
    agent = FakeAgent(final_state)
    monkeypatch.setattr("app.agent.agents.generator.create_agent", lambda *a, **k: agent)
    return ReActTestGenerator(llm=object()), agent


def test_generator_extracts_structured_files_and_harvests_external_references(monkeypatch) -> None:
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


def test_generator_caps_the_web_search_loop_with_a_tool_call_limit(monkeypatch) -> None:
    """The agent is built with a per-run tool-call limit that stops the loop gracefully."""
    captured = {}

    def fake_create_agent(_llm, **kwargs):
        captured.update(kwargs)
        return FakeAgent({"messages": [], "structured_response": _GeneratorResponse(generated_files=[])})

    monkeypatch.setattr("app.agent.agents.generator.create_agent", fake_create_agent)

    ReActTestGenerator(llm=object())

    middleware = captured["middleware"]
    assert len(middleware) == 1
    assert middleware[0].run_limit == 3
    assert middleware[0].exit_behavior == "continue"


def test_generator_revises_a_prior_proposal_against_reviewer_findings(monkeypatch) -> None:
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


def test_generator_uses_one_web_search_agent_for_both_generation_and_revision(monkeypatch) -> None:
    """A single web_search-capable agent serves both generation and revision."""
    created = []

    def fake_create_agent(_llm, tools=None, **kwargs):
        agent = FakeAgent({"messages": [], "structured_response": _GeneratorResponse(generated_files=[])})
        created.append({"agent": agent, "tools": tools or [], "system_prompt": kwargs["system_prompt"]})
        return agent

    monkeypatch.setattr("app.agent.agents.generator.create_agent", fake_create_agent)

    generator = ReActTestGenerator(llm=object())
    generator.generate(task="add tests", source_documents=[], test_documents=[])
    generator.revise(task="add tests", source_documents=[], test_documents=[], prior_files=[], diff="", findings=[])

    # Exactly one agent is constructed, it is web_search-capable, and both passes go through it.
    assert len(created) == 1
    assert len(created[0]["tools"]) == 1
    assert len(created[0]["agent"].invocations) == 2


def test_generator_revision_consults_web_search_and_harvests_references(monkeypatch) -> None:
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
