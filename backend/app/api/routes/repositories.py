"""Expose injected API endpoints for Git repository workflows."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.dependencies import CurrentUser, RepositoryServiceDep, WeaviateResourcesDep
from app.models.repository import RepositoriesPublic, Repository, RepositoryCreate, RepositoryPublic, RepositoryUpdate

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("/", response_model=RepositoriesPublic)
def read_repositories(repository_service: RepositoryServiceDep, current_user: CurrentUser, skip: int = 0, limit: int = 100) -> RepositoriesPublic:
    """Return a paginated Git repository list visible to the current user."""
    return repository_service.list_repositories(user=current_user, skip=skip, limit=limit)


@router.get("/{repository_id}", response_model=RepositoryPublic)
def read_repository(repository_service: RepositoryServiceDep, current_user: CurrentUser, repository_id: uuid.UUID) -> Repository:
    """Return one Git repository after enforcing ownership permissions."""
    return repository_service.get_repository(repository_id=repository_id, user=current_user)


@router.post("/", response_model=RepositoryPublic, status_code=status.HTTP_202_ACCEPTED)
def create_repository(
    *,
    repository_service: RepositoryServiceDep,
    current_user: CurrentUser,
    weaviate_resources: WeaviateResourcesDep,
    background_tasks: BackgroundTasks,
    repository_in: RepositoryCreate,
) -> Repository:
    """Register a Git repository and schedule its cloning and indexing."""
    return repository_service.create_repository(
        repository_in=repository_in, user=current_user, background_tasks=background_tasks, weaviate_resources=weaviate_resources
    )


@router.put("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_repository(
    *, repository_service: RepositoryServiceDep, current_user: CurrentUser, repository_id: uuid.UUID, repository_in: RepositoryUpdate
) -> Response:
    """Replace only Git repository credentials."""
    repository_service.update_repository(repository_id=repository_id, repository_in=repository_in, user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(repository_service: RepositoryServiceDep, current_user: CurrentUser, repository_id: uuid.UUID) -> None:
    """Delete Git repository state from local checkout, vector db, and relational db."""
    repository_service.delete_repository(repository_id=repository_id, user=current_user)
