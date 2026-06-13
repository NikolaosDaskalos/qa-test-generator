"""Orchestrate Git repository ingestion, retrieval, and answer generation."""

import logging
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.vector_db import WeaviateResources
from app.persistence.source_document_store import SourceDocumentStore
from app.prompts.rag_prompts import QA_SYSTEM_PROMPT
from app.rag.chain_builder import ChainBuilder
from app.rag.ingestor import DocumentIngestor
from app.rag.retriever import DocumentRetriever

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
        self.document_retriever = DocumentRetriever(self.weaviate_resources, tenant=str(user_id))
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

    def answer_stream(self, question: str, *, repository_id: uuid.UUID, history: list[dict[str, Any]] | None = None, use_hyde: bool = False) -> Generator:
        """Return a generator that streams answer events."""
        logger.info(
            "RAG answer stream requested user_id=%s repository_id=%s history_count=%s use_hyde=%s", self.user_id, repository_id, len(history or []), use_hyde
        )
        return self.chain_builder.answer_stream(question, repository_id=repository_id, history=history, use_hyde=use_hyde)

    def get_stats(self) -> dict[str, Any]:
        """Return collection statistics for this user tenant."""
        return self.document_retriever.get_stats()
