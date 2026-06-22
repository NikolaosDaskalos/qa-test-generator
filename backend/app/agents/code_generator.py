"""The bounded ReAct code generator.

The generator is a ReAct agent whose **only** tool is ``web_search`` — no shell,
no filesystem. It looks up a test framework's current syntax and best practices,
then returns structured complete-file proposals (never diff text). The loop is
bounded by single-tool binding and a per-run tool-call limit. A single agent performs
both initial generation and revision; revision may also call ``web_search``, since
many findings (e.g. a deprecated test-framework API) are exactly what a web lookup
resolves. Web results become ``External Reference``s harvested from the agent's tool
messages, kept separate from Repository Documents and never used to ground claims
about the Repository's code — only how tests are written.
"""

import json
import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.agents.middleware import build_tool_call_limit_middleware
from app.agents.tools import web_search
from app.prompts.prompts import CODE_GENERATOR_SYSTEM_PROMPT
from app.prompts.rendering import format_files, format_repository_documents
from app.schemas import ExternalReference, GeneratedFile, GenerationProposal

logger = logging.getLogger(__name__)


class _GeneratorResponse(BaseModel):
    """The agent's structured response: complete test-file proposals only.

    External References are harvested by the backend from real tool calls, not
    taken from the model's free-text output, so they are deliberately absent here.
    """

    generated_files: list[GeneratedFile] = Field(default_factory=list, description="Complete proposed test files, each a path and its full contents.")


class CodeGenerator:
    """Production ``CodeGenerator``: one web-backed agent for both generation and revision."""

    def __init__(self, llm) -> None:
        self._agent = create_agent(
            llm,
            tools=[web_search],
            system_prompt=CODE_GENERATOR_SYSTEM_PROMPT,
            response_format=_GeneratorResponse,
            middleware=[build_tool_call_limit_middleware()],
        )

    def generate(self, *, task: str, source_documents: list, test_documents: list) -> GenerationProposal:
        prompt = _build_prompt(task, source_documents, test_documents)
        return self._propose(prompt)

    def revise(self, *, task: str, source_documents: list, test_documents: list, prior_files: list, diff: str, findings: list) -> GenerationProposal:
        """Replace a rejected proposal once, grounded in the reviewer's findings.

        The reviser sees the same task and Repository Documents as initial generation
        plus its own prior complete-file proposal, the canonical diff that was
        reviewed, and the categorized findings to address, and returns a full
        replacement proposal — never a diff.
        """
        prompt = _build_revision_prompt(task, source_documents, test_documents, prior_files, diff, findings)
        return self._propose(prompt)

    def _propose(self, prompt: str) -> GenerationProposal:
        result = self._agent.invoke({"messages": [HumanMessage(content=prompt)]})
        response = result.get("structured_response")
        generated_files = response.generated_files if response else []
        return GenerationProposal(generated_files=generated_files, external_references=_references_from_messages(result.get("messages") or []))

    def __call__(self, *, task: str, source_documents: list, test_documents: list) -> GenerationProposal:
        return self.generate(task=task, source_documents=source_documents, test_documents=test_documents)


def _build_prompt(task: str, source_documents: list, test_documents: list) -> str:
    """Assemble the generation prompt from the task and partitioned Repository Documents."""
    sections = [f"Task:\n{task}"]
    if source_documents:
        sections.append("Source code under test:\n" + format_repository_documents(source_documents))
    if test_documents:
        sections.append("Existing tests:\n" + format_repository_documents(test_documents))
    return "\n\n".join(sections)


def _build_revision_prompt(task: str, source_documents: list, test_documents: list, prior_files: list, diff: str, findings: list) -> str:
    """Assemble the revision prompt: the generation context plus the rejected proposal and findings.

    The reviewer's findings frame the revision as a directed fix, and the prior
    proposal and canonical diff show exactly what was rejected so the model replaces
    it wholesale rather than guessing at the prior attempt.
    """
    sections = [_build_prompt(task, source_documents, test_documents)]
    sections.append(
        "Your previous proposal was reviewed and rejected. Address every finding below and return the complete, "
        "corrected contents of each test file; never return a diff."
    )
    if findings:
        sections.append("Reviewer findings to address:\n" + _format_findings(findings))
    if prior_files:
        sections.append("Your rejected proposal:\n" + format_files(prior_files))
    sections.append(f"Canonical diff that was reviewed:\n{diff}")
    return "\n\n".join(sections)


def _format_findings(findings: list) -> str:
    return "\n".join(f"- [{finding.category}] {finding.detail}" for finding in findings)


def _references_from_messages(messages: list) -> list[ExternalReference]:
    """Harvest de-duplicated External References from ``web_search`` tool messages."""
    references: list[ExternalReference] = []
    seen: set[str] = set()
    for message in messages:
        if getattr(message, "type", None) != "tool" or getattr(message, "name", None) != "web_search":
            continue
        for result in _parse_results(getattr(message, "content", "")):
            url = result.get("url")
            if url and url not in seen:
                seen.add(url)
                references.append(ExternalReference(url=url, title=result.get("title") or ""))
    return references


def _parse_results(content) -> list[dict]:
    """Extract the result records from a web_search tool message payload."""
    if not isinstance(content, str):
        return []
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        return []
    if isinstance(payload, dict):
        results = payload.get("results", [])
    elif isinstance(payload, list):
        results = payload
    else:
        results = []
    return [item for item in results if isinstance(item, dict)]
