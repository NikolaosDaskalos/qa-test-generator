import uuid
from pathlib import Path

from langchain_core.documents import Document

from app.rag.ingestor import DocumentIngestor


class FakeCollection:
    def __init__(self) -> None:
        self.deleted_where = None

    def delete(self, *, where) -> None:
        self.deleted_where = where


class FakeVectorStore:
    def __init__(self) -> None:
        self._collection = FakeCollection()
        self.ids: list[str] = []

    def add_documents(self, documents, *, ids) -> None:
        self.ids = ids


def test_ingestion_replaces_repository_chunks_with_deterministic_ids() -> None:
    repository_id = uuid.uuid4()
    vectorstore = FakeVectorStore()
    ingestor = DocumentIngestor.__new__(DocumentIngestor)
    ingestor.vectorstore = vectorstore
    documents = [
        Document(
            page_content="print('one')",
            metadata={"source": "one.py"},
        ),
        Document(
            page_content="print('two')",
            metadata={"source": "two.py"},
        ),
    ]
    ingestor._load = lambda *args: documents
    ingestor._split = lambda *args: documents

    first_count = ingestor.ingest(Path("/repo"), repository_id, "main")
    first_ids = list(vectorstore.ids)
    second_count = ingestor.ingest(Path("/repo"), repository_id, "main")

    assert first_count == second_count == 2
    assert vectorstore._collection.deleted_where == {
        "repository_id": str(repository_id)
    }
    assert vectorstore.ids == first_ids


def test_empty_ingestion_clears_existing_repository_chunks() -> None:
    repository_id = uuid.uuid4()
    vectorstore = FakeVectorStore()
    ingestor = DocumentIngestor.__new__(DocumentIngestor)
    ingestor.vectorstore = vectorstore
    ingestor._load = lambda *args: []

    count = ingestor.ingest(Path("/repo"), repository_id, "main")

    assert count == 0
    assert vectorstore._collection.deleted_where == {
        "repository_id": str(repository_id)
    }
