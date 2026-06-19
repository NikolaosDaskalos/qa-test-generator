"""Specify Repository Document retrieval through the public RAG interface."""

import uuid
from types import SimpleNamespace

from langchain_core.documents import Document

from app.core import WeaviateResources
from app.models import RepositoryDocument
from app.rag import DocumentRetriever


class _Store:
    def __init__(self, documents) -> None:
        self.documents = {document.id: document for document in documents}

    def get_by_id(self, document_id):
        return self.documents.get(document_id)


class _VectorStore:
    def __init__(self, chunks) -> None:
        self.chunks = chunks

    def similarity_search_with_score(self, **_kwargs):
        return [(chunk, 1.0) for chunk in self.chunks]


class _Reranker:
    def compress_documents(self, documents, _query):
        return list(reversed(documents))


def test_retrieve_documents_reranks_hydrates_and_enforces_repository_scope() -> None:
    repository_id = uuid.uuid4()
    requested_document = RepositoryDocument(repository_id=repository_id, content="requested", doc_metadata={"source": "app/requested.py"})
    foreign_document = RepositoryDocument(repository_id=uuid.uuid4(), content="foreign", doc_metadata={"source": "app/foreign.py"})
    chunks = [
        Document(page_content="requested chunk", metadata={"parent_id": str(requested_document.id)}),
        Document(page_content="foreign chunk", metadata={"parent_id": str(foreign_document.id)}),
    ]
    collection = SimpleNamespace(tenants=SimpleNamespace(get_by_names=lambda _names: {"tenant": object()}))
    resources = WeaviateResources(SimpleNamespace(collections=SimpleNamespace(get=lambda _name: collection)), _VectorStore(chunks))
    retriever = DocumentRetriever(resources, "tenant", _Store([requested_document, foreign_document]), _Reranker())

    documents = retriever.retrieve_documents("requested behavior", repository_id=repository_id, k=10, alpha=0.5, parent_limit=5)

    assert documents == [requested_document]
