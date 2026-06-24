"""The ``repository_question`` branch: Question Shape analysis and retrieval strategies.

After Request Intent routes a turn here, the ``analyzing`` node infers the Question
Shape (``simple`` | ``independent`` | ``chained``) and routes to a strategy node. The
``simple_rag`` strategy answers a single focused question with multi-query + RAG-fusion:
generate N query reformulations, fuse their raw hybrid results with Reciprocal Rank
Fusion, Cohere-rerank the fused pool against the original question, and stream a single
grounded answer via the shared generation helper. Uncertain shape falls back to
``simple`` — read-only and side-effect-free.
"""

from typing import Literal

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.fallback import model_label, with_provider_fallback
from app.agents.nodes.generation import generate_grounded_answer
from app.core import settings
from app.prompts.prompts import MULTI_QUERY_PROMPT
from app.schemas import Stage
from app.streaming import emit

QuestionShape = Literal["simple", "independent", "chained"]


class ShapeClassification(BaseModel):
    """Structured output of the ``analyzing`` node: the inferred Question Shape."""

    shape: QuestionShape = Field(
        description="The structural shape of the repository question: 'simple' for a single focused ask, "
        "'independent' for several unrelated sub-questions in one message, or 'chained' for a multi-hop "
        "question whose later parts depend on answering the earlier ones."
    )


class QueryVariants(BaseModel):
    """Structured output of multi-query reformulation: alternative search queries."""

    variants: list[str] = Field(description="Alternative search-query reformulations of the original question for hybrid code retrieval.")


def build_analyzing_node(classifier_llm, fallback_llm):
    """Build the ``analyzing`` node; uncertain classification falls back to the read-only ``simple`` shape."""
    structured = with_provider_fallback(
        classifier_llm,
        fallback_llm,
        lambda model: model.with_structured_output(ShapeClassification),
        primary_label=model_label(classifier_llm),
        fallback_label=model_label(fallback_llm),
    )

    def analyzing(state) -> dict:
        emit(Stage(stage="analyzing"))
        # Read recent Session History when present so a follow-up's shape fits the conversation.
        messages = state.get("messages") or [HumanMessage(content=state["question"])]
        result = structured.invoke(messages)
        shape: QuestionShape = result.shape if result else "simple"
        return {"question_shape": shape, "trace": ["analyzing"]}

    return analyzing


def build_simple_rag_node(retriever, llm, fallback_llm):
    """Build the ``simple_rag`` strategy: multi-query + RAG-fusion, then a single streamed answer."""
    variant_llm = with_provider_fallback(
        llm,
        fallback_llm,
        lambda model: model.with_structured_output(QueryVariants),
        primary_label=model_label(llm),
        fallback_label=model_label(fallback_llm),
    )
    answer_llm = with_provider_fallback(
        llm,
        fallback_llm,
        lambda model: model,
        primary_label=model_label(llm),
        fallback_label=model_label(fallback_llm),
    )

    def simple_rag(state) -> dict:
        emit(Stage(stage="retrieving"))
        question = state["question"]
        variants = _generate_variants(variant_llm, question)
        documents = retriever.fusion_retrieve_documents(
            variants,
            original_query=question,
            repository_id=state["repository_id"],
            k=settings.TOP_K,
            alpha=settings.HYBRID_SEARCH_ALPHA,
            parent_limit=settings.FINAL_PARENT_LIMIT,
            rrf_k=settings.RRF_K,
        )
        answer = generate_grounded_answer(answer_llm, question=question, documents=documents)
        return {"documents": documents, "trace": ["simple_rag"], **answer}

    return simple_rag


def _generate_variants(variant_llm, question: str) -> list[str]:
    """Reformulate the question into search variants, capped at the configured count.

    The structured schema does not bound the list, so a verbose or prompt-influenced
    response is de-duplicated and trimmed to ``QUERY_VARIANT_COUNT`` here — otherwise each
    extra variant would cost another vector search. Falls back to the original question
    when the model yields nothing usable.
    """
    messages = [SystemMessage(content=MULTI_QUERY_PROMPT.format(count=settings.QUERY_VARIANT_COUNT)), HumanMessage(content=question)]
    result = variant_llm.invoke(messages)
    seen: set[str] = set()
    variants: list[str] = []
    for variant in result.variants if result else []:
        cleaned = variant.strip() if variant else ""
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            variants.append(cleaned)
    return variants[: settings.QUERY_VARIANT_COUNT] or [question]
