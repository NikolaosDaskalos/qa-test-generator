"""Test document persistence operations without infrastructure."""

import uuid

from app.models.source_document import SourceDocument
from app.persistence.source_document_store import SourceDocumentStore


class FakeSession:
    """Record session mutations and transaction boundaries."""

    def __init__(self) -> None:
        self.added = []
        self.added_batches = []
        self.deleted = []
        self.commits = 0
        self.refreshes = []

    def add(self, value) -> None:
        self.added.append(value)

    def add_all(self, values) -> None:
        self.added_batches.append(values)

    def delete(self, value) -> None:
        self.deleted.append(value)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value) -> None:
        self.refreshes.append(value)


def _document() -> SourceDocument:
    return SourceDocument(
        repository_id=uuid.UUID("d72745e5-958f-436c-8fc2-d8c2596b33ee"),
        doc_metadata={"source": "backend/app/main.py"},
    )


def test_create_persists_document() -> None:
    session = FakeSession()
    document_store = SourceDocumentStore(session)
    document = _document()

    result = document_store.create(document)

    assert result is document
    assert session.added == [document]
    assert session.commits == 1
    assert session.refreshes == [document]


def test_update_persists_document() -> None:
    session = FakeSession()
    document_store = SourceDocumentStore(session)
    document = _document()
    document.doc_metadata = {"source": "backend/app/updated.py"}

    result = document_store.update(document)

    assert result is document
    assert session.added == [document]
    assert session.commits == 1
    assert session.refreshes == [document]


def test_save_all_persists_documents_in_one_batch() -> None:
    session = FakeSession()
    document_store = SourceDocumentStore(session)
    documents = [_document(), _document()]

    result = document_store.saveAll(documents)

    assert result is documents
    assert session.added_batches == [documents]
    assert session.commits == 1
    assert session.refreshes == documents


def test_delete_removes_document() -> None:
    session = FakeSession()
    document_store = SourceDocumentStore(session)
    document = _document()

    document_store.delete(document)

    assert session.deleted == [document]
    assert session.commits == 1
