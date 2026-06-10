"""Expose injected API endpoints for Git repository workflows."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.dependencies import CurrentUser, RepositoryServiceDep, WeaviateResourcesDep
from app.models.git_repositories import GitRepositoriesPublic, GitRepository, GitRepositoryCreate, GitRepositoryPublic, GitRepositoryUpdate

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("/", response_model=GitRepositoriesPublic)
def read_repositories(service: RepositoryServiceDep, current_user: CurrentUser, skip: int = 0, limit: int = 100) -> GitRepositoriesPublic:
    """Return a paginated repository list visible to the current user."""
    return service.repository_list(user=current_user, skip=skip, limit=limit)


@router.get("/{id}", response_model=GitRepositoryPublic)
def read_repository(service: RepositoryServiceDep, current_user: CurrentUser, id: uuid.UUID) -> GitRepository:
    """Return one repository after enforcing ownership permissions."""
    return service.repository_get(repository_id=id, user=current_user)


@router.post("/", response_model=GitRepositoryPublic, status_code=status.HTTP_202_ACCEPTED)
def create_repository(
    *,
    service: RepositoryServiceDep,
    current_user: CurrentUser,
    weaviate_resources: WeaviateResourcesDep,
    background_tasks: BackgroundTasks,
    repository_in: GitRepositoryCreate,
) -> GitRepository:
    """Register a repository and schedule its cloning and indexing."""
    return service.repository_create(repository=repository_in, user=current_user, background_tasks=background_tasks, weaviate_resources=weaviate_resources)


@router.put("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def update_repository(*, service: RepositoryServiceDep, current_user: CurrentUser, id: uuid.UUID, repository_in: GitRepositoryUpdate) -> Response:
    """Replace only repository credentials."""
    service.repository_update(repository_id=id, repository=repository_in, user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(service: RepositoryServiceDep, current_user: CurrentUser, id: uuid.UUID) -> None:
    """Delete repository state from local checkout, vector db, and relational db."""
    service.repository_delete(repository_id=id, user=current_user)
