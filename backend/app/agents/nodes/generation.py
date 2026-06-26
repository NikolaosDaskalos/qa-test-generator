"""Shared grounded-answer generation for the repository-question strategies.

Extracted from the original ``generate`` node so every Question Shape strategy
streams its single final answer the same way: emit the ``generating`` stage marker,
short-circuit to the insufficient-documents answer when retrieval was empty, and
otherwise stream the grounded answer (its token chunks ride LangGraph's ``messages``
stream) while collecting the text and projecting de-duplicated file citations.
"""

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, SystemMessage

from app.prompts.prompts import QA_SYSTEM_PROMPT
from app.prompts.rendering import format_repository_documents
from app.schemas import Citation, Stage
from app.streaming import FINAL_ANSWER_TAG, emit

# Returned verbatim when retrieval yields no Repository Documents, so the answer
# states the limitation instead of letting the model fill gaps from its own knowledge.
INSUFFICIENT_DOCUMENTS_ANSWER = "I don't have enough Repository Documents in this session to answer that question."


def generate_grounded_answer(answer_llm, *, question: str, documents) -> dict:
    """Stream a grounded final answer with de-duplicated citations, or report insufficient documents.

    Emits the ``generating`` stage marker, then either returns the deterministic
    insufficient-documents answer (never touching the model) when retrieval was empty,
    or streams the grounded answer — its token chunks ride LangGraph's ``messages``
    stream — collecting the full text and de-duplicated file citations onto state.
    """
    emit(Stage(stage="generating"))
    documents = documents or []
    if not documents:
        return {"answer": INSUFFICIENT_DOCUMENTS_ANSWER, "citations": []}

    context = format_repository_documents(documents)
    messages = [SystemMessage(content=f"{QA_SYSTEM_PROMPT}\n\nContext:\n{context}"), HumanMessage(content=question)]
    return stream_and_cite(answer_llm, messages=messages, documents=documents)


def stream_and_cite(answer_llm, *, messages, documents) -> dict:
    """Stream a final answer from ``messages``, collecting its text and de-duplicated citations.

    The shared streaming/citation core every Question Shape strategy reuses: the token
    chunks ride LangGraph's ``messages`` stream while the full text is collected, and the
    citations are projected from the de-duplicated parent sources of ``documents``. The
    caller owns the Stage marker (``generating`` for a single grounded answer,
    ``synthesizing`` for a decomposed one) and the message construction.

    The stream is tagged ``FINAL_ANSWER_TAG`` so ``map_graph_stream`` forwards only these
    chunks as ``Token``s: a strategy node's node-local variant/decomposition/sub-answer
    model calls run under the same ``langgraph_node`` name and must never reach the client.
    """
    collected = ""
    for chunk in answer_llm.stream(messages, config={"tags": [FINAL_ANSWER_TAG]}):
        token = getattr(chunk, "content", "") or ""
        if token:
            collected += token

    return {"answer": collected, "citations": _to_citations(_extract_sources(documents))}


def _extract_sources(docs) -> list[str]:
    """Extract source paths from selected parent RepositoryDocuments."""
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
