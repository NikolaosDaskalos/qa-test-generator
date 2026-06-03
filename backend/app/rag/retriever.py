"""
retrieval/retriever.py
----------------------
Responsible for: vector store queries, stats, and database management.
"""

from typing import Dict, Literal
import logging
from langchain_chroma import Chroma
from app.core.config import settings
from langchain_voyageai import VoyageAIEmbeddings

embedder: VoyageAIEmbeddings = VoyageAIEmbeddings(model=settings.EMBEDDING_MODEL,
                                                  output_dimension=settings.EMBEDDING_DIMENSIONS)
logger = logging.getLogger(__name__)


class VectorRetriever:
    """
    Wraps the ChromaDB vector store with retrieval, stats, and clear operations.
    Decoupled from the LLM — pure vector search layer.
    """

    def __init__(self, vectorstore, embeddings):
        self.vectorstore = vectorstore
        self.embeddings = embeddings

    def as_retriever(self, retrieval_mode: Literal["similarity", "mmr", "similarity_score_threshold"] = 'similarity',
                     k: int = 3, lambda_mult: float = 0.5):
        """Return a LangChain-compatible retriever for use in LCEL chains."""
        return self.vectorstore.as_retriever(
            search_type=retrieval_mode,
            search_kwargs={"k": k, lambda_mult: lambda_mult},
        )

        def get_stats(self) -> Dict:
            """Return chunk count and unique document sources."""
            collection = self.vectorstore._collection
            count = collection.count()
            sources = set()
            if count > 0:
                data = collection.get(include=["metadatas"])
                for m in (data.get("metadatas") or []):
                    if m and "source" in m:
                        sources.add(m["source"])
            return {
                "total_chunks": count,
                "unique_sources": len(sources),
                "sources": sorted(sources),
            }

        # TODO remove this is not needed
        def clear(self):
            """Delete all documents and recreate an empty collection."""
            self.vectorstore.delete_collection()
            logger.info("Vector store cleared.")
