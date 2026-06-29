"""The bounded Code Reviewer: structured static decision over a fake agent.

These drive the reviewer through an injected fake agent so the decision
extraction, prompt assembly, and loop boundary are verified without any real
model or network call.
"""

from types import SimpleNamespace

import anthropic
import httpx
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import tools as tools_module
from app.agents.code_reviewer import CodeReviewer
from app.db.models import RepositoryDocument
from app.schemas import GeneratedFile, PatchReview, ReviewFinding


class ScriptedToolModel(GenericFakeChatModel):
    """A fake chat model that replays scripted AIMessages and accepts ``bind_tools`` as a no-op.

    Driving the *real* ``create_agent`` + ``ToolStrategy`` loop with scripted tool calls
    exercises the production wiring — web_search interleaved with the structured-output tool
    call, and handle_errors recovery — without a real model or network.
    """

    def bind_tools(self, tools, **kwargs):
        return self


def _web_search_call(query: str, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": query}, "id": call_id}])


def _patch_review_call(args: dict, call_id: str) -> AIMessage:
    """A call to the artificial structured-output tool ToolStrategy binds for PatchReview."""
    return AIMessage(content="", tool_calls=[{"name": "PatchReview", "args": args, "id": call_id}])


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


def _anthropic_status_error(status_code: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError("boom", response=httpx.Response(status_code, request=request), body=None)


def _source(source: str, content: str) -> RepositoryDocument:
    return RepositoryDocument(content=content, doc_metadata={"source": source})


def test_patch_review_carries_a_bounded_score_and_findings_not_an_accepted_flag() -> None:
    """The reviewer scores a patch 0–10 with findings; the backend owns the pass decision, so there is no accepted flag."""
    review = PatchReview(score=8, findings=[ReviewFinding(category="coverage", detail="covers happy and unhappy paths")])

    assert review.score == 8
    assert [finding.category for finding in review.findings] == ["coverage"]
    assert "accepted" not in PatchReview.model_fields


def test_code_reviewer_returns_the_structured_score_and_findings() -> None:
    """The agent's structured response becomes the PatchReview score and findings."""
    findings = [ReviewFinding(category="coverage", detail="missing an unhappy-path test")]
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(score=5, findings=findings)})
    reviewer = CodeReviewer(llm=object(), agent=agent)

    review = reviewer.review(task="add tests", source_documents=[], test_documents=[], generated_files=[], diff="d")

    assert review.score == 5
    assert [finding.category for finding in review.findings] == ["coverage"]


def test_code_reviewer_defaults_to_a_zero_score_when_no_structured_decision_is_returned() -> None:
    """A missing structured response is scored conservatively at zero, never a silent passing score."""
    agent = FakeAgent({"messages": [], "structured_response": None})
    reviewer = CodeReviewer(llm=object(), agent=agent)

    review = reviewer.review(task="add tests", source_documents=[], test_documents=[], generated_files=[], diff="d")

    assert review.score == 0


def test_code_reviewer_prompt_includes_the_task_proposals_and_diff() -> None:
    """The review prompt carries the task, the documents, the proposed files, and the canonical diff."""
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(score=9, findings=[])})
    reviewer = CodeReviewer(llm=object(), agent=agent)

    reviewer.review(
        task="add auth tests",
        source_documents=[_source("app/auth.py", "def login(): ...")],
        test_documents=[],
        generated_files=[GeneratedFile(path="tests/test_auth.py", content="def test_login(): ...")],
        diff="diff --git a/tests/test_auth.py b/tests/test_auth.py",
    )

    agent_input, _config = agent.invocations[0]
    prompt = agent_input["messages"][0]
    assert isinstance(prompt, HumanMessage)
    assert "add auth tests" in prompt.content
    assert "app/auth.py" in prompt.content
    assert "tests/test_auth.py" in prompt.content
    assert "diff --git" in prompt.content


def test_code_reviewer_caps_the_web_search_loop_with_a_tool_call_limit(monkeypatch) -> None:
    """The default agent is built with a per-run tool-call limit that stops the loop gracefully."""
    captured = {}

    def fake_create_agent(_llm, **kwargs):
        captured.update(kwargs)
        return FakeAgent({"messages": [], "structured_response": PatchReview(score=9, findings=[])})

    monkeypatch.setattr("app.agents.code_reviewer.create_agent", fake_create_agent)

    CodeReviewer(llm=object())

    middleware = captured["middleware"]
    assert len(middleware) == 1
    assert middleware[0].run_limit == 3
    assert middleware[0].exit_behavior == "continue"


def test_code_reviewer_requests_structured_output_via_a_tool_strategy_not_native_parsing(monkeypatch) -> None:
    """The agent asks for PatchReview through a ToolStrategy (a distinct structured-output tool call), never a raw schema.

    A raw ``response_format=PatchReview`` resolves to native provider structured output on
    Anthropic — a json.loads of the post-tool turn that fails when it isn't bare JSON (the
    intermittent StructuredOutputValidationError of issue #46). A ToolStrategy keeps the
    schema distinct from web_search and carries handle_errors, so a bad extraction is fed
    back for a bounded retry rather than crashing the reviewing stage.
    """
    captured = {}

    def fake_create_agent(_llm, **kwargs):
        captured.update(kwargs)
        return FakeAgent({"messages": [], "structured_response": PatchReview(score=9, findings=[])})

    monkeypatch.setattr("app.agents.code_reviewer.create_agent", fake_create_agent)

    CodeReviewer(llm=object())

    response_format = captured["response_format"]
    assert isinstance(response_format, ToolStrategy)
    assert response_format.schema is PatchReview
    assert response_format.handle_errors  # the built-in bounded retry on a parse failure


def test_code_reviewer_produces_valid_structured_output_from_a_tool_using_review(monkeypatch) -> None:
    """A real review that calls web_search and then the structured-output tool yields a valid PatchReview.

    Drives the production ``create_agent`` + ``ToolStrategy`` loop end to end: web_search and
    the structured score+findings coexist without the native-JSON failure of issue #46.
    """
    monkeypatch.setattr(tools_module, "emit", lambda event: None)
    monkeypatch.setattr(tools_module, "_tavily_search", SimpleNamespace(invoke=lambda payload: {"results": [{"url": "https://docs.pytest.org"}]}))
    model = ScriptedToolModel(
        messages=iter(
            [
                _web_search_call("pytest fixtures best practices", "s1"),
                _patch_review_call({"score": 8, "findings": [{"category": "coverage", "detail": "covers both paths"}]}, "r1"),
            ]
        )
    )
    reviewer = CodeReviewer(llm=model)

    review = reviewer.review(task="add tests", source_documents=[], test_documents=[], generated_files=[], diff="d")

    assert review.score == 8
    assert [finding.category for finding in review.findings] == ["coverage"]


def test_code_reviewer_recovers_when_the_first_structured_extraction_fails_to_validate(monkeypatch) -> None:
    """A first structured-output tool call that fails PatchReview validation is fed back and retried, recovering to a valid review.

    This is the bounded retry the reviewing stage relies on (issue #46): ToolStrategy's
    handle_errors turns a schema-invalid extraction into a corrective message instead of a
    Run Failure, and the next attempt produces a valid PatchReview.
    """
    monkeypatch.setattr(tools_module, "emit", lambda event: None)
    model = ScriptedToolModel(
        messages=iter(
            [
                _patch_review_call({"score": 99, "findings": []}, "bad"),  # score > 10 fails PatchReview validation
                _patch_review_call({"score": 6, "findings": []}, "good"),
            ]
        )
    )
    reviewer = CodeReviewer(llm=model)

    review = reviewer.review(task="add tests", source_documents=[], test_documents=[], generated_files=[], diff="d")

    assert review.score == 6


def test_code_reviewer_falls_over_to_the_fallback_provider_on_a_transient_error(monkeypatch) -> None:
    """A transient failure in the primary (Anthropic) reviewer re-runs review on the gpt-4o-mini fallback agent."""

    def fake_create_agent(llm, **kwargs):
        if llm == "primary":
            return RaisingAgent(_anthropic_status_error(529))
        return FakeAgent({"messages": [], "structured_response": PatchReview(score=8, findings=[])})

    monkeypatch.setattr("app.agents.code_reviewer.create_agent", fake_create_agent)
    reviewer = CodeReviewer(llm="primary", fallback_llm="fallback")

    review = reviewer.review(task="add tests", source_documents=[], test_documents=[], generated_files=[], diff="d")

    assert review.score == 8


def test_code_reviewer_fails_fast_on_a_deterministic_error_without_the_fallback(monkeypatch) -> None:
    """A deterministic primary failure (400) is not masked by the fallback; the reviewer surfaces it."""
    fallback_invoked = {"count": 0}

    def fake_create_agent(llm, **kwargs):
        if llm == "primary":
            return RaisingAgent(_anthropic_status_error(400))

        class _Counting(FakeAgent):
            def invoke(self, agent_input, config=None):
                fallback_invoked["count"] += 1
                return super().invoke(agent_input, config)

        return _Counting({"messages": [], "structured_response": PatchReview(score=8, findings=[])})

    monkeypatch.setattr("app.agents.code_reviewer.create_agent", fake_create_agent)
    reviewer = CodeReviewer(llm="primary", fallback_llm="fallback")

    try:
        reviewer.review(task="add tests", source_documents=[], test_documents=[], generated_files=[], diff="d")
    except anthropic.APIStatusError:
        pass
    else:
        raise AssertionError("expected the deterministic 400 to propagate")

    assert fallback_invoked["count"] == 0
