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
from app.agents.nodes.generation import INSUFFICIENT_DOCUMENTS_ANSWER, generate_grounded_answer, stream_and_cite
from app.core import settings
from app.prompts.prompts import DECOMPOSE_PROMPT, MULTI_QUERY_PROMPT, SUB_ANSWER_PROMPT, SYNTHESIS_PROMPT
from app.prompts.rendering import format_repository_documents
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


class SubQuestions(BaseModel):
    """Structured output of decomposition: the independent sub-questions a compound message splits into."""

    sub_questions: list[str] = Field(
        description="Independent, self-contained sub-questions that together cover the compound question; each must stand alone "
        "as a hybrid code-retrieval query and not depend on the answer to another."
    )


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


def build_decompose_parallel_node(retriever, llm, fallback_llm):
    """Build the ``decompose_parallel`` strategy for ``independent`` questions.

    Splits a compound message into independent sub-questions (capped), retrieves for each
    with the existing single-query hybrid+rerank retrieval (one query each, in a loop),
    answers them all in one batched model call, then streams a single synthesized final
    answer. Sub-questions and sub-answers stay node-local; only the synthesized answer
    streams as tokens, and its citations are the de-duplicated union of parent sources
    across every sub-question retrieval.
    """
    decompose_llm = with_provider_fallback(
        llm,
        fallback_llm,
        lambda model: model.with_structured_output(SubQuestions),
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

    def decompose_parallel(state) -> dict:
        emit(Stage(stage="decomposing"))
        question = state["question"]
        repository_id = state["repository_id"]
        sub_questions = _decompose(decompose_llm, question)
        retrievals = [
            retriever.retrieve_documents(
                sub_question,
                repository_id=repository_id,
                k=settings.TOP_K,
                alpha=settings.HYBRID_SEARCH_ALPHA,
                parent_limit=settings.FINAL_PARENT_LIMIT,
            )
            for sub_question in sub_questions
        ]
        merged = _merge_documents(retrievals)
        if not merged:
            # Every sub-question retrieved nothing: report the limitation, never the model.
            return {"documents": [], "trace": ["decompose_parallel"], "answer": INSUFFICIENT_DOCUMENTS_ANSWER, "citations": []}

        sub_answers = _answer_sub_questions(answer_llm, sub_questions, retrievals)
        emit(Stage(stage="synthesizing"))
        messages = [
            SystemMessage(content=SYNTHESIS_PROMPT.format(qa_pairs=_format_qa_pairs(sub_questions, sub_answers))),
            HumanMessage(content=question),
        ]
        answer = stream_and_cite(answer_llm, messages=messages, documents=merged)
        return {"documents": merged, "trace": ["decompose_parallel"], **answer}

    return decompose_parallel


def _decompose(decompose_llm, question: str) -> list[str]:
    """Split a compound question into independent sub-questions, capped at the configured maximum.

    The structured schema does not bound the list, so a verbose or prompt-influenced
    response is de-duplicated and trimmed to ``MAX_SUB_QUESTIONS`` here — otherwise each
    extra sub-question would cost another retrieval. Falls back to the original question
    when the model yields nothing usable.
    """
    messages = [SystemMessage(content=DECOMPOSE_PROMPT.format(count=settings.MAX_SUB_QUESTIONS)), HumanMessage(content=question)]
    result = decompose_llm.invoke(messages)
    seen: set[str] = set()
    sub_questions: list[str] = []
    for sub_question in result.sub_questions if result else []:
        cleaned = sub_question.strip() if sub_question else ""
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            sub_questions.append(cleaned)
    return sub_questions[: settings.MAX_SUB_QUESTIONS] or [question]


def _merge_documents(retrievals: list[list]) -> list:
    """Union the per-sub-question parent documents, de-duplicated by id in first-seen order."""
    merged: list = []
    seen: set = set()
    for documents in retrievals:
        for document in documents:
            if document.id not in seen:
                seen.add(document.id)
                merged.append(document)
    return merged


def _answer_sub_questions(answer_llm, sub_questions: list[str], retrievals: list[list]) -> list[str]:
    """Answer every sub-question from its own retrieved context in one batched model call (never streamed)."""
    batched_messages = [
        [
            SystemMessage(content=SUB_ANSWER_PROMPT.format(context=format_repository_documents(documents))),
            HumanMessage(content=sub_question),
        ]
        for sub_question, documents in zip(sub_questions, retrievals, strict=True)
    ]
    results = answer_llm.batch(batched_messages)
    return [getattr(result, "content", "") or "" for result in results]


def _format_qa_pairs(sub_questions: list[str], sub_answers: list[str]) -> str:
    """Render the node-local sub-question/sub-answer pairs for the synthesis prompt."""
    return "\n\n".join(f"Q: {sub_question}\nA: {sub_answer}" for sub_question, sub_answer in zip(sub_questions, sub_answers, strict=True))
