import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.dependencies import CurrentUser, SessionDep
from app.models.todo import Todo
from app.schemas.authentication import Message
from app.schemas.todo import TodoCreate, TodoPublic, TodosPublic, TodoUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("/", response_model=TodosPublic)
def read_todos(session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100) -> Any:
    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(Todo)
        count = session.exec(count_statement).one()

        statement = select(Todo).offset(skip).limit(limit)
        todos = session.exec(statement).all()

    else:
        count_statement = select(func.count()).select_from(Todo).where(Todo.owner_id == current_user.id)
        count = session.exec(count_statement).one()

        statement = select(Todo).where(Todo.owner_id == current_user.id).offset(skip).limit(limit)
        todos = session.exec(statement).all()

    logger.info("Todos listed user_id=%s returned_count=%s total_count=%s", current_user.id, len(todos), count)
    return TodosPublic(data=todos, count=count)  # type: ignore[arg-type]


@router.get("/{id}", response_model=TodoPublic)
def read_todo(session: SessionDep, current_user: CurrentUser, id: uuid.UUID) -> Any:
    todo = session.get(Todo, id)

    if not todo:
        logger.warning("Todo lookup failed because it was not found todo_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=404, detail="Todo not found")

    if not current_user.is_superuser and todo.owner_id != current_user.id:
        logger.warning("Todo access denied todo_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=403, detail="Not enough permissions")

    logger.info("Todo retrieved todo_id=%s user_id=%s", id, current_user.id)
    return todo


@router.post("/", response_model=TodoPublic)
def create_todo(*, session: SessionDep, current_user: CurrentUser, todo_in: TodoCreate) -> Any:
    todo = Todo.model_validate(todo_in, update={"owner_id": current_user.id})

    session.add(todo)
    session.commit()
    session.refresh(todo)

    logger.info("Todo created todo_id=%s owner_id=%s", todo.id, current_user.id)
    return todo


@router.put("/{id}", response_model=TodoPublic)
def update_todo(*, session: SessionDep, current_user: CurrentUser, id: uuid.UUID, todo_in: TodoUpdate) -> Any:
    todo = session.get(Todo, id)

    if not todo:
        logger.warning("Todo update failed because it was not found todo_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=404, detail="Todo not found")

    if not current_user.is_superuser and todo.owner_id != current_user.id:
        logger.warning("Todo update denied todo_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=403, detail="Not enough permissions")

    update_dict = todo_in.model_dump(exclude_unset=True)
    todo.sqlmodel_update(update_dict)

    session.add(todo)
    session.commit()
    session.refresh(todo)

    logger.info("Todo updated todo_id=%s user_id=%s fields=%s", todo.id, current_user.id, sorted(update_dict))
    return todo


@router.delete("/{id}", response_model=Message)
def delete_todo(session: SessionDep, current_user: CurrentUser, id: uuid.UUID) -> Message:
    todo = session.get(Todo, id)

    if not todo:
        logger.warning("Todo deletion failed because it was not found todo_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=404, detail="Todo not found")

    if not current_user.is_superuser and todo.owner_id != current_user.id:
        logger.warning("Todo deletion denied todo_id=%s user_id=%s", id, current_user.id)
        raise HTTPException(status_code=403, detail="Not enough permissions")

    session.delete(todo)
    session.commit()

    logger.info("Todo deleted todo_id=%s user_id=%s", id, current_user.id)
    return Message(message="Todo deleted successfully")
