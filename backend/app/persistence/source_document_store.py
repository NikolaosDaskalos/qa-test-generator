import uuid

from sqlmodel import Session, select

from app.models.source_document import SourceDocument


class SourceDocumentStore:
    """Persist document records through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, source_document_id: uuid.UUID) -> SourceDocument | None:
        return self.session.get(SourceDocument, source_document_id)

    def get_by_repository_id(self, repository_id: uuid.UUID) -> list[SourceDocument]:
        statement = select(SourceDocument).where(SourceDocument.repository_id == repository_id)
        return list(self.session.exec(statement).all())

    def get_page(self, *, skip: int, limit: int, repository_id: uuid.UUID | None = None) -> list[SourceDocument]:
        statement = select(SourceDocument)
        if repository_id is not None:
            statement = statement.where(SourceDocument.repository_id == repository_id)
        statement = statement.offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def save(self, source_document: SourceDocument) -> SourceDocument:
        self.session.add(source_document)
        self.session.commit()
        self.session.refresh(source_document)
        return source_document

    def save_all(self, source_documents: list[SourceDocument]) -> list[SourceDocument]:
        self.session.add_all(source_documents)
        self.session.commit()
        return source_documents

    def delete(self, document: SourceDocument) -> None:
        self.session.delete(document)
        self.session.commit()
