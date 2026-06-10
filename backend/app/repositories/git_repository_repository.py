import uuid
from datetime import datetime

from sqlmodel import Session, func, select

from app.models.git_repositories import GitRepository, GitRepositoryStatus


class GitRepositoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, repository_id: uuid.UUID) -> GitRepository | None:
        return self.session.get(GitRepository, repository_id)

    def get_by_user_id(self, user_id: uuid.UUID) -> list[GitRepository]:
        statement = select(GitRepository).where(GitRepository.user_id == user_id)
        return list(self.session.exec(statement).all())

    def get_page(self, *, skip: int, limit: int, user_id: uuid.UUID | None = None) -> list[GitRepository]:
        statement = select(GitRepository)
        if user_id is not None:
            statement = statement.where(GitRepository.user_id == user_id)
        statement = statement.offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def count(self, *, user_id: uuid.UUID | None = None) -> int:
        statement = select(func.count()).select_from(GitRepository)
        if user_id is not None:
            statement = statement.where(GitRepository.user_id == user_id)
        return self.session.exec(statement).one()

    def get_by_url_and_user_id(self, repository_url: str, user_id: uuid.UUID) -> GitRepository | None:
        statement = select(GitRepository).where(GitRepository.user_id == user_id, GitRepository.repository_url == repository_url)
        return self.session.exec(statement).first()

    def save(self, repository: GitRepository) -> GitRepository:
        self.session.add(repository)
        self.session.commit()
        self.session.refresh(repository)
        return repository

    def update_token(self, repository: GitRepository, *, encrypted_token: str, token_expiration_date: datetime | None) -> GitRepository:
        repository.encrypted_token = encrypted_token
        repository.token_expiration_date = token_expiration_date
        return self.save(repository)

    def delete(self, repository: GitRepository) -> None:
        self.session.delete(repository)
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def update_status(self, repository: GitRepository, status: GitRepositoryStatus, *, failed_reason: str | None = None) -> GitRepository:
        repository.status = status
        repository.failed_reason = failed_reason
        return self.save(repository)
