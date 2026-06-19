"""The PostgreSQL store for indexed source documents (the Postgres side of the RAG index)."""

import uuid

from sqlmodel import Session, col, delete, select

from app.models import SourceDocument


class SourceDocumentStore:
    """Persist document records through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, source_document_id: uuid.UUID) -> SourceDocument | None:
        """Load a source document by id, or ``None`` if absent."""
        return self.session.get(SourceDocument, source_document_id)

    def get_by_repository_id(self, repository_id: uuid.UUID) -> list[SourceDocument]:
        """Return all source documents indexed for one repository."""
        statement = select(SourceDocument).where(SourceDocument.repository_id == repository_id)
        return list(self.session.exec(statement).all())

    def get_page(self, *, skip: int, limit: int, repository_id: uuid.UUID | None = None) -> list[SourceDocument]:
        """Return a page of source documents, optionally scoped to one repository."""
        statement = select(SourceDocument)
        if repository_id is not None:
            statement = statement.where(SourceDocument.repository_id == repository_id)
        statement = statement.offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def save(self, source_document: SourceDocument) -> SourceDocument:
        """Persist a single source document and return the refreshed row."""
        self.session.add(source_document)
        self.session.commit()
        self.session.refresh(source_document)
        return source_document

    def save_all(self, source_documents: list[SourceDocument]) -> list[SourceDocument]:
        """Persist a batch of source documents in one commit."""
        self.session.add_all(source_documents)
        self.session.commit()
        return source_documents

    def replace_for_repository(self, repository_id: uuid.UUID, source_documents: list[SourceDocument]) -> list[SourceDocument]:
        """Replace one Repository's persisted source documents atomically."""
        try:
            self.session.exec(delete(SourceDocument).where(col(SourceDocument.repository_id) == repository_id))
            self.session.add_all(source_documents)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return source_documents

    def delete_by_repository(self, repository_id: uuid.UUID) -> None:
        """Delete all source documents belonging to one Repository."""
        try:
            self.session.exec(delete(SourceDocument).where(col(SourceDocument.repository_id) == repository_id))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete(self, document: SourceDocument) -> None:
        """Delete a single source document."""
        self.session.delete(document)
        self.session.commit()
