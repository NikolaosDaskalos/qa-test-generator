import uuid
from datetime import datetime

from sqlmodel import Session, func, select

from app.enums.repository import RepositoryStatus
from app.models.repository import Repository


class RepositoryStore:
    """Persist Git repository records through a SQLModel session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, repository_id: uuid.UUID) -> Repository | None:
        return self.session.get(Repository, repository_id)

    def get_by_user_id(self, user_id: uuid.UUID) -> list[Repository]:
        statement = select(Repository).where(Repository.user_id == user_id)
        return list(self.session.exec(statement).all())

    def get_page(self, *, skip: int, limit: int, user_id: uuid.UUID | None = None) -> list[Repository]:
        statement = select(Repository)
        if user_id is not None:
            statement = statement.where(Repository.user_id == user_id)
        statement = statement.offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def count(self, *, user_id: uuid.UUID | None = None) -> int:
        statement = select(func.count()).select_from(Repository)
        if user_id is not None:
            statement = statement.where(Repository.user_id == user_id)
        return self.session.exec(statement).one()

    def get_by_url_and_user_id(self, repository_url: str, user_id: uuid.UUID) -> Repository | None:
        statement = select(Repository).where(Repository.user_id == user_id, Repository.repository_url == repository_url)
        return self.session.exec(statement).first()

    def save(self, repository: Repository) -> Repository:
        self.session.add(repository)
        self.session.commit()
        self.session.refresh(repository)
        return repository

    def update_token(self, repository: Repository, *, encrypted_token: str, token_expiration_date: datetime | None) -> Repository:
        repository.encrypted_token = encrypted_token
        repository.token_expiration_date = token_expiration_date
        return self.save(repository)

    def delete(self, repository: Repository) -> None:
        self.session.delete(repository)
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def update_status(self, repository: Repository, status: RepositoryStatus, *, failed_reason: str | None = None) -> Repository:
        repository.status = status
        repository.failed_reason = failed_reason
        return self.save(repository)
