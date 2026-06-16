"""The bounded ReAct test generator: structured files + harvested External References.

These drive the generator through an injected fake agent so the loop boundary,
structured-file extraction, and External Reference harvesting are verified without
any real model or network call.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.generator import ReActTestGenerator, _GeneratorResponse
from app.schemas.generation import GeneratedFile


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


def test_generator_extracts_structured_files_and_harvests_external_references() -> None:
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
    agent = FakeAgent(final_state)
    generator = ReActTestGenerator(llm=object(), agent=agent, recursion_limit=7)

    proposal = generator.generate(task="add tests for auth", source_evidence=[], test_evidence=[])

    assert [file.path for file in proposal.generated_files] == ["tests/test_auth.py"]
    assert [reference.url for reference in proposal.external_references] == ["https://docs.pytest.org"]


def test_generator_caps_the_web_search_loop_with_a_recursion_limit() -> None:
    """The agent is invoked under the configured recursion limit, bounding the tool loop."""
    final_state = {"messages": [], "structured_response": _GeneratorResponse(generated_files=[])}
    agent = FakeAgent(final_state)
    generator = ReActTestGenerator(llm=object(), agent=agent, recursion_limit=5)

    generator.generate(task="add tests", source_evidence=[], test_evidence=[])

    _agent_input, config = agent.invocations[0]
    assert config["recursion_limit"] == 5
