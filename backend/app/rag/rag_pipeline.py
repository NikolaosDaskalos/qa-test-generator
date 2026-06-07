"""
rag_pipeline.py — Orchestrator
-------------------------------
Wires together the three components:
  ingestion.ingestor.DocumentIngestor   → load + split + store
  retrieval.retriever.VectorRetriever   → search + stats + clear
  generation.chain_builder.ChainBuilder → LCEL chain + streaming

LangSmith traces automatically when LANGCHAIN_TRACING_V2=true in .env.
"""

import logging
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_voyageai import VoyageAIEmbeddings

from app.core.config import settings
from app.prompts.rag_prompts import QA_SYSTEM_PROMPT
from app.rag.chain_builder import ChainBuilder
from app.rag.ingestor import DocumentIngestor
from app.rag.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Top-level orchestrator.
    Delegates every responsibility to a specialised component.
    """

    def __init__(self):
        # ── Shared infrastructure ────────────────────────────────
        self.embeddings = VoyageAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            output_dimension=settings.EMBEDDING_DIMENSIONS,
            api_key=settings.VOYAGE_API_KEY,
        )
        self.vectorstore = Chroma(
            collection_name="documents",
            embedding_function=self.embeddings,
            persist_directory=str(settings.CHROMA_DB_PATH),
        )
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
            streaming=True,
            api_key=settings.OPENAI_API_KEY,
        )

        # ── Components ───────────────────────────────────────────
        self.ingestor = DocumentIngestor(self.vectorstore)
        self.v_retriever = VectorRetriever(self.vectorstore, self.embeddings)
        self.chain_builder = ChainBuilder(self.llm, self.vectorstore)

    # ── Public API (delegates to components) ─────────────────────

    def set_system_prompt(self, prompt: str):
        self.chain_builder.build(system_prompt=prompt.strip() or QA_SYSTEM_PROMPT)

    def ingest(
        self,
        repo_path: Path,
        repository_id: uuid.UUID,
        branch: str,
    ) -> int:
        return self.ingestor.ingest(repo_path, repository_id, branch)

    def answer_stream(
        self,
        question: str,
        history: list[dict[str, Any]] | None = None,
        use_hyde: bool = False,
    ) -> Generator:
        return self.chain_builder.answer_stream(question, history, use_hyde)

    def get_stats(self) -> dict[str, Any]:
        return self.v_retriever.get_stats()

    # TODO delete this
    # def clear(self):
    #     self.v_retriever.clear()
    #     # ── Sync the NEW vectorstore to ALL components ────────────────
    #     new_vs = self.v_retriever.vectorstore
    #     self.vectorstore = new_vs
    #     self.ingestor.vectorstore = new_vs  # ← was missing! caused the error
    #     self.chain_builder.vectorstore = new_vs
    #     self.chain_builder.build()


# TODO remove it after finish testing
# if __name__ == "__main__":
#     rag = RAGPipeline()
#     rag.ingest("git@github.com:NikolaosDaskalos/fastapi-heroes-app.git")
#     for event in rag.answer_stream("How can I delete a Hero? What can block me from deleting it?"):
#         if event["type"] == "token":
#             print(event["content"], end="", flush=True)
#         elif event["type"] == "status":
#             print(event["message"])
#         elif event["type"] == "done":
#             print("\n\nSources:", event["sources"])
#             print("Token info:", event["token_info"])
