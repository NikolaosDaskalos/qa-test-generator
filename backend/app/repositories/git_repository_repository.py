import uuid
from sqlmodel import select

from app.dependencies import SessionDep
from app.models import GitRepository


class GitRepositoryRepository:
    def __init__(self, session: SessionDep):
        self.session = session

    def get_by_id(self, repository_id: uuid.UUID):
        return self.session.get(GitRepository, repository_id)

    def get_by_user_id(self, user_id: uuid.UUID):
        return select(GitRepository).where(GitRepository.user_id == user_id)

    def get_by_name_and_user_id(self, name: str, user_id: uuid.UUID):
        return select(GitRepository).where(GitRepository.user_id == user_id, GitRepository.name == name).limit(1)

    def get_all(self, skip: int, limit: int):
        statement = select(GitRepository)
        statement = statement.offset(skip).limit(limit)
        results = self.session.exec(statement)

        return results.all()

    def save(self, repository: GitRepository):
        self.session.add(repository)
        self.session.commit()
        self.session.refresh(repository)
