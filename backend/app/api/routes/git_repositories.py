import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.dependencies import CurrentUser, SessionDep
from app.models.git_repositories import GitRepositoryPublic, GitRepositoriesPublic, GitRepository, GitRepositoryCreate

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("/", response_model=GitRepositoriesPublic)
def read_repositories(
        session: SessionDep,
        current_user: CurrentUser,
        skip: int = 0,
        limit: int = 100,
) -> Any:
    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(GitRepository)
        count = session.exec(count_statement).one()

        statement = select(GitRepository).offset(skip).limit(limit)
        repositories = session.exec(statement).all()

    else:
        count_statement = (
            select(func.count())
            .select_from(GitRepository)
            .where(GitRepository.user_id == current_user.id)
        )
        count = session.exec(count_statement).one()

        statement = (
            select(GitRepository)
            .where(GitRepository.user_id == current_user.id)
            .offset(skip)
            .limit(limit)
        )
        repositories = session.exec(statement).all()

    return GitRepositoriesPublic(data=repositories, count=count)


@router.get("/{id}", response_model=GitRepositoryPublic)
def read_repository(
        session: SessionDep,
        current_user: CurrentUser,
        id: uuid.UUID,
) -> Any:
    repository = session.get(GitRepository, id)

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    if not current_user.is_superuser and repository.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return repository


@router.post("/", response_model=GitRepositoryPublic)
def create_repository(
        *,
        session: SessionDep,
        current_user: CurrentUser,
        repository_in: GitRepositoryCreate,
) -> Any:
    repository = GitRepository.model_validate(
        repository_in,
        update={"user_id": current_user.id},
    )

    session.add(repository)
    session.commit()
    session.refresh(repository)

    return repository

# @router.put("/{id}", response_model=TodoPublic)
# def update_todo(
#         *,
#         session: SessionDep,
#         current_user: CurrentUser,
#         id: uuid.UUID,
#         todo_in: TodoUpdate,
# ) -> Any:
#     todo = session.get(Todo, id)
#
#     if not todo:
#         raise HTTPException(status_code=404, detail="Todo not found")
#
#     if not current_user.is_superuser and todo.owner_id != current_user.id:
#         raise HTTPException(status_code=403, detail="Not enough permissions")
#
#     update_dict = todo_in.model_dump(exclude_unset=True)
#     todo.sqlmodel_update(update_dict)
#
#     session.add(todo)
#     session.commit()
#     session.refresh(todo)
#
#     return todo
#
#
# @router.delete("/{id}", response_model=Message)
# def delete_todo(
#         session: SessionDep,
#         current_user: CurrentUser,
#         id: uuid.UUID,
# ) -> Message:
#     todo = session.get(Todo, id)
#
#     if not todo:
#         raise HTTPException(status_code=404, detail="Todo not found")
#
#     if not current_user.is_superuser and todo.owner_id != current_user.id:
#         raise HTTPException(status_code=403, detail="Not enough permissions")
#
#     session.delete(todo)
#     session.commit()
#
#     return Message(message="Todo deleted successfully")
