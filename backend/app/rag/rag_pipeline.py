"""Orchestrate Git repository ingestion, retrieval, and answer generation."""

import logging
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

from langchain_cohere import CohereRerank
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings
from app.core.vector_db import WeaviateResources
from app.persistence.source_document_store import SourceDocumentStore
from app.prompts.rag_prompts import QA_SYSTEM_PROMPT
from app.rag.chain_builder import ChainBuilder
from app.rag.ingestor import DocumentIngestor
from app.rag.retriever import DocumentRetriever
from app.schemas.agent_stream import AgentStreamEvent

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Coordinate the RAG components for a single user tenant."""

    def __init__(self, user_id: uuid.UUID, weaviate_resources: WeaviateResources, source_document_store: SourceDocumentStore):
        """Initialize model, ingestion, retrieval, and chain components."""
        self.user_id = user_id
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL, temperature=settings.TEMPERATURE, max_tokens=settings.MAX_TOKENS, streaming=True, api_key=settings.OPENAI_API_KEY
        )

        # ── Components ───────────────────────────────────────────
        self.weaviate_resources = weaviate_resources
        self.ingestor = DocumentIngestor(self.weaviate_resources, source_document_store)
        reranker = CohereRerank(
            model=settings.COHERE_RERANK_MODEL, cohere_api_key=SecretStr(settings.COHERE_API_KEY), top_n=settings.TOP_K
        )
        self.document_retriever = DocumentRetriever(self.weaviate_resources, str(user_id), source_document_store, reranker)
        self.chain_builder = ChainBuilder(self.llm, self.document_retriever)
        logger.info("RAG pipeline initialized user_id=%s model=%s", user_id, settings.LLM_MODEL)

    # ── Public API (delegates to components) ─────────────────────

    def set_system_prompt(self, prompt: str):
        """Set the answer persona, falling back to the default prompt."""
        self.chain_builder.build(system_prompt=prompt.strip() or QA_SYSTEM_PROMPT)
        logger.info("RAG system prompt configured user_id=%s custom_prompt=%s", self.user_id, bool(prompt.strip()))

    def ingest(self, repo_path: Path, repository_id: uuid.UUID, branch: str, commit_sha: str) -> int:
        """Index a Git repository for this pipeline's user tenant."""
        logger.info("RAG pipeline ingestion requested user_id=%s repository_id=%s branch=%s", self.user_id, repository_id, branch)
        return self.ingestor.ingest(repo_path, repository_id, branch, commit_sha, self.user_id)

    def answer_stream(self, question: str, *, repository_id: uuid.UUID, history: list[dict[str, Any]] | None = None) -> Generator[AgentStreamEvent, None, None]:
        """Return a generator that streams typed Agent Stream events."""
        logger.info("RAG answer stream requested user_id=%s repository_id=%s history_count=%s", self.user_id, repository_id, len(history or []))
        return self.chain_builder.answer_stream(question, repository_id=repository_id, history=history)

    def get_stats(self, *, repository_id: uuid.UUID) -> dict[str, Any]:
        """Return collection statistics for one Repository."""
        return self.document_retriever.get_stats(repository_id=repository_id)
