"""The bounded ReAct Patch Reviewer: structured static decision over a fake agent.

These drive the reviewer through an injected fake agent so the decision
extraction, prompt assembly, and loop boundary are verified without any real
model or network call.
"""

from langchain_core.messages import HumanMessage

from app.agent.agents.reviewer import ReActPatchReviewer
from app.models.source_document import SourceDocument
from app.schemas.generation import GeneratedFile
from app.schemas.review import PatchReview, ReviewFinding


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


def test_reviewer_returns_the_structured_decision() -> None:
    """The agent's structured response becomes the PatchReview decision and findings."""
    findings = [ReviewFinding(category="coverage", detail="missing an unhappy-path test")]
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(accepted=False, findings=findings)})
    reviewer = ReActPatchReviewer(llm=object(), agent=agent, recursion_limit=7)

    review = reviewer.review(task="add tests", source_evidence=[], test_evidence=[], generated_files=[], diff="d")

    assert review.accepted is False
    assert [finding.category for finding in review.findings] == ["coverage"]


def test_reviewer_defaults_to_rejection_when_no_structured_decision_is_returned() -> None:
    """A missing structured response is treated conservatively as a rejection, never a silent accept."""
    agent = FakeAgent({"messages": [], "structured_response": None})
    reviewer = ReActPatchReviewer(llm=object(), agent=agent)

    review = reviewer.review(task="add tests", source_evidence=[], test_evidence=[], generated_files=[], diff="d")

    assert review.accepted is False


def test_reviewer_prompt_includes_the_task_proposals_and_diff() -> None:
    """The review prompt carries the task, the evidence, the proposed files, and the canonical diff."""
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(accepted=True, findings=[])})
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


def test_reviewer_caps_the_web_search_loop_with_a_recursion_limit() -> None:
    """The agent is invoked under the configured recursion limit, bounding the tool loop."""
    agent = FakeAgent({"messages": [], "structured_response": PatchReview(accepted=True, findings=[])})
    reviewer = ReActPatchReviewer(llm=object(), agent=agent, recursion_limit=5)

    reviewer.review(task="add tests", source_evidence=[], test_evidence=[], generated_files=[], diff="d")

    _agent_input, config = agent.invocations[0]
    assert config["recursion_limit"] == 5
