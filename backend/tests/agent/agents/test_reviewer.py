"""The bounded ReAct Patch Reviewer: structured static decision over a fake agent.

These drive the reviewer through an injected fake agent so the decision
extraction, prompt assembly, and loop boundary are verified without any real
model or network call.
"""

from langchain_core.messages import HumanMessage

from app.agent.agents.reviewer import ReActPatchReviewer
from app.models import SourceDocument
from app.schemas import GeneratedFile, PatchReview, ReviewFinding


class FakeAgent:
    """A stand-in compiled agent that records its invocation and returns a final state."""

    def __init__(self, final_state) -> None:
        self.final_state = final_state
        self.invocations = []

    def invoke(self, agent_input, config=None):
        self.invocations.append((agent_input, config))
        return self.final_state


def _source(source: str, content: str) -> SourceDocument:
    return SourceDocument(content=content, doc_metadata={"source": source})


def test_patch_review_carries_a_bounded_score_and_findings_not_an_accepted_flag() -> None:
    """The reviewer scores a patch 0–10 with findings; the backend owns the pass decision, so there is no accepted flag."""
    review = PatchReview(score=8, findings=[ReviewFinding(category="coverage", detail="covers happy and unhappy paths")])

    assert review.score == 8
    assert [finding.category for finding in review.findings] == ["coverage"]
    assert "accepted" not in PatchReview.model_fields


def test_reviewer_returns_the_structured_score_and_findings() -> None:
    """The agent's structured response becomes the PatchReview score and findings."""
    findings = [ReviewFinding(category="coverage", detail="missing an unhappy-path test")]
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(score=5, findings=findings)})
    reviewer = ReActPatchReviewer(llm=object(), agent=agent)

    review = reviewer.review(task="add tests", source_evidence=[], test_evidence=[], generated_files=[], diff="d")

    assert review.score == 5
    assert [finding.category for finding in review.findings] == ["coverage"]


def test_reviewer_defaults_to_a_zero_score_when_no_structured_decision_is_returned() -> None:
    """A missing structured response is scored conservatively at zero, never a silent passing score."""
    agent = FakeAgent({"messages": [], "structured_response": None})
    reviewer = ReActPatchReviewer(llm=object(), agent=agent)

    review = reviewer.review(task="add tests", source_evidence=[], test_evidence=[], generated_files=[], diff="d")

    assert review.score == 0


def test_reviewer_prompt_includes_the_task_proposals_and_diff() -> None:
    """The review prompt carries the task, the evidence, the proposed files, and the canonical diff."""
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(score=9, findings=[])})
    reviewer = ReActPatchReviewer(llm=object(), agent=agent)

    reviewer.review(
        task="add auth tests",
        source_evidence=[_source("app/auth.py", "def login(): ...")],
        test_evidence=[],
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


def test_reviewer_caps_the_web_search_loop_with_a_tool_call_limit(monkeypatch) -> None:
    """The default agent is built with a per-run tool-call limit that stops the loop gracefully."""
    captured = {}

    def fake_create_agent(_llm, **kwargs):
        captured.update(kwargs)
        return FakeAgent({"messages": [], "structured_response": PatchReview(score=9, findings=[])})

    monkeypatch.setattr("app.agent.agents.reviewer.create_agent", fake_create_agent)

    ReActPatchReviewer(llm=object())

    middleware = captured["middleware"]
    assert len(middleware) == 1
    assert middleware[0].run_limit == 3
    assert middleware[0].exit_behavior == "continue"
