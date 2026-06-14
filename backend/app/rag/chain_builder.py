"""Build LCEL chains and stream retrieval answers."""

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
from app.schemas.agent_stream import Sources, Token

logger = logging.getLogger(__name__)

# Returned verbatim when retrieval yields no Repository Evidence, so the answer
# states the limitation instead of letting the model fill gaps from its own knowledge.
INSUFFICIENT_EVIDENCE_ANSWER = "I don't have enough Repository Evidence in this session to answer that question."


class ChainBuilder:
    """Build and own LCEL chains for retrieval-grounded answers."""

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

    def answer_stream(self, question: str, *, repository_id: uuid.UUID, history: list[dict] | None = None) -> Generator:
        """Stream answer events using history-aware retrieval.

        Yields:
            Typed Agent Stream events: ``Token`` chunks followed by a terminal
            ``Sources`` event carrying the retrieved source paths.

        """
        lc_history = self._to_lc_messages(history or [])
        logger.info("RAG answer generation started history_message_count=%s", len(lc_history))

        yield from self._stream_standard(question, repository_id, lc_history)

    # ── Retrieval-grounded answering ──────────────────────────────

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
        if not evidence:
            logger.warning("Standard RAG retrieval returned no documents")
            yield from self._stream_insufficient_evidence(question)
            return

        sources = self._extract_sources(evidence)
        context = self._format_docs(evidence)
        logger.info("Standard RAG retrieval completed evidence_count=%s", len(evidence))

        # Step 3: Build prompt and stream answer
        qa_prompt = ChatPromptTemplate.from_messages(
            [("system", self._system_prompt + "\n\nContext:\n{context}"), MessagesPlaceholder("chat_history"), ("human", "{input}")]
        )

        collected = ""
        for token in (qa_prompt | self.llm | StrOutputParser()).stream({"input": question, "chat_history": lc_history, "context": context}):
            collected += token
            yield Token(content=token)

        logger.info("Standard RAG answer generation completed source_count=%s response_length=%s", len(sources), len(collected))
        yield Sources(sources=sources)

    # ── Helpers ───────────────────────────────────────────────────

    def _stream_insufficient_evidence(self, question: str) -> Generator:
        """Stream a deterministic answer with no citations when evidence is empty."""
        yield Token(content=INSUFFICIENT_EVIDENCE_ANSWER)
        yield Sources(sources=[])

    @staticmethod
    def _format_docs(docs) -> str:
        """Format retrieved documents as source-labeled prompt context."""
        return "\n\n---\n\n".join(f"[Source: {document.doc_metadata.get('source', '?')}]\n{document.content}" for document in docs)

    @staticmethod
    def _extract_sources(docs) -> list[str]:
        """Extract source paths from selected parent SourceDocuments."""
        return [document.doc_metadata.get("source", "Unknown") for document in docs]

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
