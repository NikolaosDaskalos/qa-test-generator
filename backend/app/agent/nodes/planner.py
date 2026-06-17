"""The ``test_generation`` planner node.

The planner validates that the request is about adding or improving tests and,
when it is, emits the Research Intents the run should gather evidence for. An
out-of-scope (or uncommitted) request is rejected here as a terminal
``RunFailure(failed_stage=CodingRunStage.planning)`` before any retrieval or generation.
"""

from pydantic import BaseModel, Field

from app.enums.coding_run import CodingRunStage
from app.schemas.agent_stream import RunFailure
from app.schemas.research_intent import ResearchIntent

# Used when the planner rejects scope without a specific, sanitized reason.
DEFAULT_REJECTION_REASON = "This request is outside the scope of adding or improving tests."


class PlannerOutput(BaseModel):
    """The planner's structured LLM output: scope verdict plus Research Intents."""

    in_scope: bool = Field(description="Whether the request is specifically about adding, fixing, or improving tests.")
    intents: list[ResearchIntent] = Field(
        default_factory=list,
        description="Evidence-gathering intents to execute when the request is in scope; include both source and test evidence when useful.",
    )
    reason: str | None = Field(
        default=None,
        description="Short user-safe explanation when the request is out of scope; leave null for in-scope requests.",
    )


def build_plan_node(planner_llm):
    """Build the planner node from a structured-output language model."""
    structured = planner_llm.with_structured_output(PlannerOutput)

    def plan(state) -> dict:
        result = structured.invoke(state["question"])
        if result is None or not result.in_scope:
            reason = (result.reason if result and result.reason else None) or DEFAULT_REJECTION_REASON
            return {"failure": RunFailure(failed_stage=CodingRunStage.planning, reason=reason), "trace": ["plan"]}
        return {"research_intents": result.intents, "trace": ["plan"]}

    return plan
