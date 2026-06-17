"""The bounded ReAct Patch Reviewer.

The reviewer is a ReAct agent whose **only** tool is ``web_search`` — no shell, no
filesystem, and it never executes the generated tests or installs dependencies.
Patch Review is evidence-based static assessment: it grounds claims about the code
under test only in the provided Repository Evidence, and uses ``web_search`` solely
to confirm a test framework's current syntax and best practices so it can judge
whether the proposed tests are idiomatic and version-appropriate. It returns a
structured accept/reject decision with categorized, human-readable findings. The
loop is bounded by single-tool binding and a graph recursion cap.
"""

import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.agent.context_rendering import format_evidence, format_files
from app.agent.tools import web_search
from app.schemas.review import PatchReview
from app.prompts.prompts import REVIEWER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# A single-tool ReAct loop cannot run away, but the recursion cap is the hard
# ceiling on alternating model/tool steps.
DEFAULT_RECURSION_LIMIT = 12


class ReActPatchReviewer:
    """Production ``PatchReviewer``: a bounded ``create_agent`` loop over ``web_search``."""

    def __init__(self, llm, *, recursion_limit: int = DEFAULT_RECURSION_LIMIT, agent=None) -> None:
        self._recursion_limit = recursion_limit
        self._agent = agent or create_agent(llm, tools=[web_search], system_prompt=REVIEWER_SYSTEM_PROMPT, response_format=PatchReview)

    def review(self, *, task: str, source_evidence: list, test_evidence: list, generated_files: list, diff: str) -> PatchReview:
        prompt = _build_prompt(task, source_evidence, test_evidence, generated_files, diff)
        result = self._agent.invoke({"messages": [HumanMessage(content=prompt)]}, config={"recursion_limit": self._recursion_limit})
        review = result.get("structured_response")
        return review if review is not None else PatchReview(accepted=False, findings=[])

    def __call__(self, *, task: str, source_evidence: list, test_evidence: list, generated_files: list, diff: str) -> PatchReview:
        return self.review(task=task, source_evidence=source_evidence, test_evidence=test_evidence, generated_files=generated_files, diff=diff)


def _build_prompt(task: str, source_evidence: list, test_evidence: list, generated_files: list, diff: str) -> str:
    """Assemble the review prompt from the task, partitioned evidence, and the proposed patch."""
    sections = [f"Task:\n{task}"]
    if source_evidence:
        sections.append("Source code under test:\n" + format_evidence(source_evidence))
    if test_evidence:
        sections.append("Existing tests:\n" + format_evidence(test_evidence))
    if generated_files:
        sections.append("Proposed test files:\n" + format_files(generated_files))
    sections.append(f"Canonical diff:\n{diff}")
    return "\n\n".join(sections)
