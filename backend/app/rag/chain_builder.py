"""Build LCEL chains and stream standard or HyDE retrieval answers."""

import logging
import uuid
from collections.abc import Generator

# pyrefly: ignore [missing-import]
from langchain_core.messages import AIMessage, HumanMessage

# pyrefly: ignore [missing-import]
from langchain_core.output_parsers import StrOutputParser

# pyrefly: ignore [missing-import]
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.config import settings

# pyrefly: ignore [missing-import]
from app.prompts.rag_prompts import CONTEXTUALIZE_PROMPT, QA_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
# TODO change this
COST_PER_TOKEN = 0.00000015

# Prompt used to generate the hypothetical document in HyDE mode
HYDE_PROMPT_TEMPLATE = "Write a short, factual passage (2-4 sentences) that directly answers the following question. Imagine this is an excerpt from a relevant document.\n\nQuestion: {question}\n\nPassage:"


class ChainBuilder:
    """Build and own LCEL chains for standard and HyDE retrieval modes."""

    def __init__(self, llm, retriever):
        """Initialize the builder with a language model and retriever."""
        self.llm = llm
        self.retriever = retriever
        self._system_prompt = QA_SYSTEM_PROMPT
        self.chain = None
        self.build()

    # ── Chain Construction ────────────────────────────────────────

    def build(self, system_prompt: str | None = None):
        """Build contextualization prompts and optionally update the persona."""
        if system_prompt is not None:
            self._system_prompt = system_prompt
            logger.info("RAG chain system prompt updated")

        # History-aware reformulation prompt (used in _stream_standard)
        self._ctx_prompt = ChatPromptTemplate.from_messages([("system", CONTEXTUALIZE_PROMPT), MessagesPlaceholder("chat_history"), ("human", "{input}")])

    # ── Public streaming entry point ──────────────────────────────

    def answer_stream(self, question: str, *, repository_id: uuid.UUID, history: list[dict] | None = None, use_hyde: bool = False) -> Generator:
        """Stream answer events using standard or HyDE retrieval.

        Yields:
            Status, token, and completion event dictionaries.

        """
        lc_history = self._to_lc_messages(history or [])
        logger.info("RAG answer generation started mode=%s history_message_count=%s", "hyde" if use_hyde else "standard", len(lc_history))

        if use_hyde:
            yield from self._stream_hyde(question, repository_id, lc_history)
        else:
            yield from self._stream_standard(question, repository_id, lc_history)

    # ── Standard RAG ──────────────────────────────────────────

    def _stream_standard(self, question: str, repository_id: uuid.UUID, lc_history: list) -> Generator:
        """Stream history-aware retrieval and generation events."""
        # Step 1: Reformulate question if there is chat history
        search_query = question
        if lc_history:
            logger.info("Reformulating RAG query using conversation history")
            search_query = (self._ctx_prompt | self.llm | StrOutputParser()).invoke({"input": question, "chat_history": lc_history})

        # Step 2: Retrieve complete parent Repository Evidence
        evidence = self.retriever.retrieve_evidence(
            search_query,
            repository_id=repository_id,
            k=settings.TOP_K,
            alpha=settings.HYBRID_SEARCH_ALPHA,
            parent_limit=settings.FINAL_PARENT_LIMIT,
        )
        sources = self._extract_sources(evidence)
        context = self._format_docs(evidence)
        logger.info("Standard RAG retrieval completed evidence_count=%s", len(evidence))
        if not evidence:
            logger.warning("Standard RAG retrieval returned no documents")

        # Step 3: Build prompt and stream answer
        qa_prompt = ChatPromptTemplate.from_messages(
            [("system", self._system_prompt + "\n\nContext:\n{context}"), MessagesPlaceholder("chat_history"), ("human", "{input}")]
        )

        collected = ""
        for token in (qa_prompt | self.llm | StrOutputParser()).stream({"input": question, "chat_history": lc_history, "context": context}):
            collected += token
            yield {"type": "token", "content": token}

        logger.info("Standard RAG answer generation completed source_count=%s response_length=%s", len(sources), len(collected))
        yield self._done_event(question, collected, sources, hypothetical_doc=None)

    # ── HyDE RAG ─────────────────────────────────────────────────

    def _stream_hyde(self, question: str, repository_id: uuid.UUID, lc_history: list) -> Generator:
        """Stream HyDE generation, retrieval, and answer events."""
        # Signal the UI immediately so it shows a status (not a frozen screen)
        yield {"type": "status", "message": "⚗️ Generating hypothetical document…"}

        # Step 1 — Generate hypothetical document
        logger.info("HyDE hypothetical document generation started")
        hypothetical_doc = self._generate_hypothetical_doc(question)
        logger.info("HyDE hypothetical document generation completed document_length=%s", len(hypothetical_doc))

        # Step 2 — Retrieve complete parent Repository Evidence
        evidence = self.retriever.retrieve_evidence(
            hypothetical_doc,
            repository_id=repository_id,
            k=settings.TOP_K,
            alpha=settings.HYBRID_SEARCH_ALPHA,
            parent_limit=settings.FINAL_PARENT_LIMIT,
        )
        sources = self._extract_sources(evidence)
        context = self._format_docs(evidence)
        logger.info("HyDE retrieval completed evidence_count=%s", len(evidence))
        if not evidence:
            logger.warning("HyDE retrieval returned no documents")

        # Step 3 — Build a one-shot prompt (no chain needed, context is already ready)
        qa_prompt = ChatPromptTemplate.from_messages(
            [("system", self._system_prompt + "\n\nContext:\n{context}"), MessagesPlaceholder("chat_history"), ("human", "{input}")]
        )

        # Step 4 — Stream the answer
        collected = ""
        for token in (qa_prompt | self.llm | StrOutputParser()).stream({"input": question, "chat_history": lc_history, "context": context}):
            collected += token
            yield {"type": "token", "content": token}

        logger.info("HyDE answer generation completed source_count=%s response_length=%s", len(sources), len(collected))
        yield self._done_event(question, collected, sources, hypothetical_doc)

    # ── Helpers ───────────────────────────────────────────────────

    def _generate_hypothetical_doc(self, question: str) -> str:
        """Ask the LLM to write a passage that would answer the question."""
        prompt = ChatPromptTemplate.from_template(HYDE_PROMPT_TEMPLATE)
        return (prompt | self.llm | StrOutputParser()).invoke({"question": question})

    @staticmethod
    def _format_docs(docs) -> str:
        """Format retrieved documents as source-labeled prompt context."""
        return "\n\n---\n\n".join(f"[Source: {document.doc_metadata.get('source', '?')}]\n{document.content}" for document in docs)

    @staticmethod
    def _extract_sources(docs) -> list:
        """Extract citations from selected parent SourceDocuments."""
        return [
            {
                "source": document.doc_metadata.get("source", "Unknown"),
                "page": document.doc_metadata.get("page", ""),
                "chunk": document.content,
                "score": None,
            }
            for document in docs
        ]

    @staticmethod
    def _done_event(question: str, collected: str, sources: list, hypothetical_doc: str | None) -> dict:
        """Build the final stream event with sources and estimated cost."""
        est_tokens = (len(question) + len(collected)) // 4
        return {
            "type": "done",
            "sources": sources,
            "token_info": f"~{est_tokens} tokens | ~${est_tokens * COST_PER_TOKEN:.5f}",
            "hypothetical_doc": hypothetical_doc,
        }

    @staticmethod
    def _to_lc_messages(history: list[dict]):
        """Convert persisted {role, content} dicts to LangChain message objects."""
        messages = []
        for msg in history[-6:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if "---\n📚" in content:
                content = content.split("---\n📚")[0].strip()
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        return messages
