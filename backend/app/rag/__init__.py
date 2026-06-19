"""Retrieval-augmented generation: ingestion and retrieval, re-exported as one surface."""

from app.rag.ingestor import DocumentIngestor
from app.rag.retriever import DocumentRetriever

__all__ = ["DocumentIngestor", "DocumentRetriever"]
