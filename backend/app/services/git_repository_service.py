import logging
from os import name
from uuid import UUID

from app.git.git_commands import GitCommands
from fastapi import HTTPException
import giturlparse
from app.repositories.git_repository_repository import GitRepositoryRepository
from app.models.git_repositories import GitRepository, GitRepositoryStatus, GitRepositoryProvider
from app.rag.ingestor import DocumentIngestor

logger = logging.getLogger(__name__)


class RepositoryService:

    def __init__(self, db_repo: GitRepositoryRepository, ingestor: DocumentIngestor):
        self.db_repo: GitRepositoryRepository = db_repo
        self.ingestor: DocumentIngestor = ingestor

    def repository_create(self, repo_url: str, user_id: UUID) -> GitRepository:
        parsed_url = giturlparse.parse(repo_url)

        if not parsed_url.valid:
            raise HTTPException(status_code=422, detail="Invalid repository URL")

        git: GitCommands = GitCommands(repo_url)
        clone_result = git.clone()
        logger.info(f"{repo_url} Cloned")

        if clone_result and clone_result.exit_code != 0:
            raise HTTPException(status_code=422, detail="Repository clone failed")

        if not clone_result:
            repo = self.db_repo.get_by_name_and_user_id(parsed_url.name, user_id)
            if not repo:
                repository = GitRepository(
                    user_id=user_id,
                    name=parsed_url.name,
                    repository_url=parsed_url.url,
                    owner=parsed_url.owner,
                    provider=GitRepositoryProvider(parsed_url.platform),
                    default_branch=git.get_default_branch(),
                    local_path=str(git.repo_path),
                    status=GitRepositoryStatus.pending,
                )
            else:
                return repo

        repository = GitRepository(
            user_id=user_id,
            name=parsed_url.name,
            repository_url=parsed_url.url,
            owner=parsed_url.owner,
            provider=GitRepositoryProvider(parsed_url.platform),
            default_branch=git.get_default_branch(),
            local_path=str(git.repo_path),
            status=GitRepositoryStatus.pending,
        )

        self.db_repo.save(repository)

        return repository
