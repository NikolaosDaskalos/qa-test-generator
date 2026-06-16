"""The ``test_generation`` generic retrieve node.

This node executes the planner's Research Intents under the session's Repository
identity. Each intent's untrusted candidate paths are confined to the checkout
(unsafe ones dropped) before any survive into state as validated retrieval hints.
Retrieved Repository Evidence is partitioned by the intent's tag into separate
``source_evidence`` (what's implemented) and ``test_evidence`` (what's already
tested), which are kept apart on the shared state.
"""

from pathlib import Path

from app.agent.paths import confine_candidate_paths
from app.core.config import settings


def build_gather_evidence_node(retriever):
    """Build the generic retrieve node that partitions evidence source vs. test."""

    def gather_evidence(state) -> dict:
        repository_id = state["repository_id"]
        checkout_root = state.get("checkout_root")
        source_evidence: list = []
        test_evidence: list = []
        hints: list[str] = []

        for intent in state.get("research_intents") or []:
            if checkout_root and intent.candidate_paths:
                hints.extend(confine_candidate_paths(Path(checkout_root), intent.candidate_paths))
            evidence = retriever.retrieve_evidence(
                intent.description,
                repository_id=repository_id,
                k=settings.TOP_K,
                alpha=settings.HYBRID_SEARCH_ALPHA,
                parent_limit=settings.FINAL_PARENT_LIMIT,
            )
            target = source_evidence if intent.target == "source" else test_evidence
            target.extend(evidence)

        return {
            "source_evidence": source_evidence,
            "test_evidence": test_evidence,
            "candidate_hints": _dedupe(hints),
            "trace": ["gather_evidence"],
        }

    return gather_evidence


def _dedupe(paths: list[str]) -> list[str]:
    """Drop duplicate validated hints while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered
