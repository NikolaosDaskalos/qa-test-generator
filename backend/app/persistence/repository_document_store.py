"""The PostgreSQL store for indexed Repository Documents."""

import uuid

from sqlmodel import Session, col, delete, select

from app.models import RepositoryDocument


class RepositoryDocumentStore:
    """Persist document records through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, document_id: uuid.UUID) -> RepositoryDocument | None:
        """Load a Repository Document by id, or ``None`` if absent."""
        return self.session.get(RepositoryDocument, document_id)

    def get_by_repository_id(self, repository_id: uuid.UUID) -> list[RepositoryDocument]:
        """Return all Repository Documents indexed for one Repository."""
        statement = select(RepositoryDocument).where(RepositoryDocument.repository_id == repository_id)
        return list(self.session.exec(statement).all())

    def get_page(self, *, skip: int, limit: int, repository_id: uuid.UUID | None = None) -> list[RepositoryDocument]:
        """Return a page of Repository Documents, optionally scoped to one Repository."""
        statement = select(RepositoryDocument)
        if repository_id is not None:
            statement = statement.where(RepositoryDocument.repository_id == repository_id)
        statement = statement.offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def save(self, document: RepositoryDocument) -> RepositoryDocument:
        """Persist one Repository Document and return the refreshed row."""
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def save_all(self, documents: list[RepositoryDocument]) -> list[RepositoryDocument]:
        """Persist a batch of Repository Documents in one commit."""
        self.session.add_all(documents)
        self.session.commit()
        return documents

    def replace_for_repository(self, repository_id: uuid.UUID, documents: list[RepositoryDocument]) -> list[RepositoryDocument]:
        """Replace one Repository's persisted documents atomically."""
        try:
            self.session.exec(delete(RepositoryDocument).where(col(RepositoryDocument.repository_id) == repository_id))
            self.session.add_all(documents)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return documents

    def delete_by_repository(self, repository_id: uuid.UUID) -> None:
        """Delete all Repository Documents belonging to one Repository."""
        try:
            self.session.exec(delete(RepositoryDocument).where(col(RepositoryDocument.repository_id) == repository_id))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete(self, document: RepositoryDocument) -> None:
        """Delete one Repository Document."""
        self.session.delete(document)
        self.session.commit()
