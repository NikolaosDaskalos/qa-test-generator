"""The ``repository_question`` branch nodes: retrieval-grounded answering.

The ``retrieve`` node scopes Repository Evidence to the session's Repository; the
``generate`` node streams the grounded answer (its token chunks ride LangGraph's
``messages`` stream mode) and records the answer text plus de-duplicated file
citations on the shared state.
"""

from app.agent.context_rendering import format_evidence
from app.agent.stream import emit
from app.core.config import settings
from app.prompts.prompts import QA_SYSTEM_PROMPT
from app.schemas.agent_stream import Citation, Stage

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, SystemMessage

# Returned verbatim when retrieval yields no Repository Evidence, so the answer
# states the limitation instead of letting the model fill gaps from its own knowledge.
INSUFFICIENT_EVIDENCE_ANSWER = "I don't have enough Repository Evidence in this session to answer that question."


def build_retrieve_node(retriever):
    """Build the repository-scoped retrieve node."""

    def retrieve(state) -> dict:
        emit(Stage(stage="retrieving"))
        evidence = retriever.retrieve_evidence(
            state["question"],
            repository_id=state["repository_id"],
            k=settings.TOP_K,
            alpha=settings.HYBRID_SEARCH_ALPHA,
            parent_limit=settings.FINAL_PARENT_LIMIT,
        )
        return {"evidence": evidence, "trace": ["retrieve"]}

    return retrieve


def build_generate_node(llm):
    """Build the grounded generate node that streams an answer with citations."""

    def generate(state) -> dict:
        emit(Stage(stage="generating"))
        evidence = state.get("evidence") or []
        if not evidence:
            return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "citations": [], "trace": ["generate"]}

        context = format_evidence(evidence)
        messages = [
            SystemMessage(content=f"{QA_SYSTEM_PROMPT}\n\nContext:\n{context}"),
            HumanMessage(content=state["question"]),
        ]
        collected = ""
        for chunk in llm.stream(messages):
            token = getattr(chunk, "content", "") or ""
            if token:
                collected += token

        return {"answer": collected, "citations": _to_citations(_extract_sources(evidence)), "trace": ["generate"]}

    return generate


def _extract_sources(docs) -> list[str]:
    """Extract source paths from selected parent SourceDocuments."""
    return [document.doc_metadata.get("source", "Unknown") for document in docs]


def _to_citations(sources: list[str]) -> list[Citation]:
    """Project retrieved source paths into file citations, de-duplicated in order."""
    citations: list[Citation] = []
    seen: set[str] = set()
    for path in sources:
        if path and path not in seen:
            seen.add(path)
            citations.append(Citation(source=path))
    return citations
