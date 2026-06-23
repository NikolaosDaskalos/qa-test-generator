"""The bounded ReAct Code Reviewer.

The reviewer is a ReAct agent whose **only** tool is ``web_search`` — no shell, no
filesystem, and it never executes the generated tests or installs dependencies.
Patch Review is document-grounded static assessment: it grounds claims about the code
under test only in the provided Repository Documents, and uses ``web_search`` solely
to confirm a test framework's current syntax and best practices so it can judge
whether the proposed tests are idiomatic and version-appropriate. It returns a
structured quality score out of ten with categorized, human-readable findings;
the backend, not the reviewer, decides whether that score passes. The loop is
bounded by single-tool binding and a per-run tool-call limit.
"""

import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.agents.fallback import with_agent_fallback
from app.agents.middleware import build_tool_call_limit_middleware
from app.agents.tools import web_search
from app.prompts.prompts import CODE_REVIEWER_SYSTEM_PROMPT
from app.prompts.rendering import format_files, format_repository_documents
from app.schemas import PatchReview

logger = logging.getLogger(__name__)


class CodeReviewer:
    """Production ``CodeReviewer``: a bounded ``create_agent`` loop over ``web_search``.

    When a ``fallback_llm`` is supplied the reviewer runs as a primary agent with a
    cross-provider fallback agent composed via ``with_agent_fallback``: a transient
    primary failure (e.g. an Anthropic 529) re-runs the whole bounded review on the
    fallback provider, while a deterministic failure fails fast (see ADR 0010).
    """

    def __init__(self, llm, *, fallback_llm=None, agent=None) -> None:
        if agent is not None:
            self._agent = agent
        elif fallback_llm is not None:
            self._agent = with_agent_fallback(
                _build_agent(llm), _build_agent(fallback_llm), primary_label=_model_label(llm), fallback_label=_model_label(fallback_llm)
            )
        else:
            self._agent = _build_agent(llm)

    def review(self, *, task: str, source_documents: list, test_documents: list, generated_files: list, diff: str) -> PatchReview:
        prompt = _build_prompt(task, source_documents, test_documents, generated_files, diff)
        result = self._agent.invoke({"messages": [HumanMessage(content=prompt)]})
        review = result.get("structured_response")
        return review if review is not None else PatchReview(score=0, findings=[])

    def __call__(self, *, task: str, source_documents: list, test_documents: list, generated_files: list, diff: str) -> PatchReview:
        return self.review(task=task, source_documents=source_documents, test_documents=test_documents, generated_files=generated_files, diff=diff)


def _build_agent(llm):
    """Build a bounded ReAct review agent over ``web_search`` for the given chat model."""
    return create_agent(
        llm, tools=[web_search], system_prompt=CODE_REVIEWER_SYSTEM_PROMPT, response_format=PatchReview, middleware=[build_tool_call_limit_middleware()]
    )


def _model_label(llm) -> str:
    """A human-readable model id for fallback logging (e.g. ``claude-haiku-4-5``)."""
    return getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__


def _build_prompt(task: str, source_documents: list, test_documents: list, generated_files: list, diff: str) -> str:
    """Assemble the review prompt from the task, partitioned documents, and the proposed patch."""
    sections = [f"Task:\n{task}"]
    if source_documents:
        sections.append("Source code under test:\n" + format_repository_documents(source_documents))
    if test_documents:
        sections.append("Existing tests:\n" + format_repository_documents(test_documents))
    if generated_files:
        sections.append("Proposed test files:\n" + format_files(generated_files))
    sections.append(f"Canonical diff:\n{diff}")
    return "\n\n".join(sections)
