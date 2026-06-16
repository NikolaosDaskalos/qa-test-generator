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

from app.agent.tools import web_search
from app.schemas.review import PatchReview

logger = logging.getLogger(__name__)

# A single-tool ReAct loop cannot run away, but the recursion cap is the hard
# ceiling on alternating model/tool steps.
DEFAULT_RECURSION_LIMIT = 12

REVIEWER_SYSTEM_PROMPT = (
    "You are a senior test engineer reviewing a proposed Python Test Patch. Assess it statically against the "
    "Test-Generation Task and the provided Repository Evidence only — never execute the tests, install "
    "dependencies, or claim anything about runtime behavior. Use the web_search tool only to confirm a test "
    "framework's current syntax and best practices, never to learn about the repository's own code.\n\n"
    "Check that: the tests fully exercise the source under test on both happy and unhappy paths; they are "
    "readable (readability always outranks terseness) and follow the repository's existing test conventions; "
    "every import is visible in the Repository Evidence; the patch contains no changes unrelated to the task; "
    "it stays within Test File scope and touches no application code; and it uses current, version-appropriate "
    "language and framework features, preferring cleaner utilities only when they improve readability.\n\n"
    "Return a structured decision: accepted true or false, with categorized, human-readable findings."
)


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
        sections.append("Source code under test:\n" + _format_evidence(source_evidence))
    if test_evidence:
        sections.append("Existing tests:\n" + _format_evidence(test_evidence))
    if generated_files:
        sections.append("Proposed test files:\n" + _format_files(generated_files))
    sections.append(f"Canonical diff:\n{diff}")
    return "\n\n".join(sections)


def _format_evidence(evidence: list) -> str:
    return "\n\n---\n\n".join(f"[Source: {document.doc_metadata.get('source', '?')}]\n{document.content}" for document in evidence)


def _format_files(generated_files: list) -> str:
    return "\n\n---\n\n".join(f"[File: {file.path}]\n{file.content}" for file in generated_files)
