import uuid

from sqlmodel import Session, select

from app.models.git_repositories import GitRepository, GitRepositoryStatus


class GitRepositoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, repository_id: uuid.UUID) -> GitRepository | None:
        return self.session.get(GitRepository, repository_id)

    def get_by_user_id(self, user_id: uuid.UUID) -> list[GitRepository]:
        statement = select(GitRepository).where(GitRepository.user_id == user_id)
        return list(self.session.exec(statement).all())

    def get_by_url_and_user_id(
        self,
        repository_url: str,
        user_id: uuid.UUID,
    ) -> GitRepository | None:
        statement = select(GitRepository).where(
            GitRepository.user_id == user_id,
            GitRepository.repository_url == repository_url,
        )
        return self.session.exec(statement).first()

    def get_all(self, skip: int, limit: int) -> list[GitRepository]:
        statement = select(GitRepository).offset(skip).limit(limit)
        return list(self.session.exec(statement).all())

    def save(self, repository: GitRepository) -> GitRepository:
        self.session.add(repository)
        self.session.commit()
        self.session.refresh(repository)
        return repository

    def update_status(
        self,
        repository: GitRepository,
        status: GitRepositoryStatus,
        *,
        failed_reason: str | None = None,
    ) -> GitRepository:
        repository.status = status
        repository.failed_reason = failed_reason
        return self.save(repository)
