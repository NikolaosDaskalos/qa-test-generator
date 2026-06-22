"""User routes: admin CRUD over users and self-service profile, password, and signup."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, func, select

from app import crud
from app.core import get_password_hash, settings, verify_password
from app.db.models import User
from app.dependencies import CurrentUser, SessionDep, get_current_active_superuser
from app.schemas import Message, UpdatePassword, UserCreate, UserPublic, UserRegister, UsersPublic, UserUpdate, UserUpdateMe
from app.utils import generate_new_account_email, send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", dependencies=[Depends(get_current_active_superuser)], response_model=UsersPublic)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users.
    """

    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    users = session.exec(statement).all()

    users_public = [UserPublic.model_validate(user) for user in users]
    logger.info("Users listed returned_count=%s total_count=%s", len(users_public), count)
    return UsersPublic(data=users_public, count=count)


@router.post("/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic)
def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Create new user.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        logger.warning("User creation rejected because the email is already registered existing_user_id=%s", user.id)
        raise HTTPException(status_code=400, detail="The user with this email already exists in the system.")

    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(email_to=user_in.email, username=user_in.email, password=user_in.password)
        send_email(email_to=user_in.email, subject=email_data.subject, html_content=email_data.html_content)
    logger.info("User created by administrator user_id=%s", user.id)
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(*, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser) -> Any:
    """
    Update own user.
    """

    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            logger.warning(
                "Current user update rejected because the email is already registered user_id=%s existing_user_id=%s", current_user.id, existing_user.id
            )
            raise HTTPException(status_code=409, detail="User with this email already exists")
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    logger.info("Current user updated user_id=%s fields=%s", current_user.id, sorted(user_data))
    return current_user


@router.patch("/me/password", response_model=Message)
def update_password_me(*, session: SessionDep, body: UpdatePassword, current_user: CurrentUser) -> Any:
    """
    Update own password.
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        logger.warning("Password change rejected because the current password is incorrect user_id=%s", current_user.id)
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        logger.warning("Password change rejected because the new password matches the current password user_id=%s", current_user.id)
        raise HTTPException(status_code=400, detail="New password cannot be the same as the current one")
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    logger.info("Current user password changed user_id=%s", current_user.id)
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.delete("/me", response_model=Message)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        logger.warning("Self-deletion rejected for superuser user_id=%s", current_user.id)
        raise HTTPException(status_code=403, detail="Super users are not allowed to delete themselves")
    session.delete(current_user)
    session.commit()
    logger.info("User deleted own account user_id=%s", current_user.id)
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        logger.warning("User registration rejected because the email is already registered existing_user_id=%s", user.id)
        raise HTTPException(status_code=400, detail="The user with this email already exists in the system")
    user_create = UserCreate.model_validate(user_in)
    user = crud.create_user(session=session, user_create=user_create)
    logger.info("User registered user_id=%s", user.id)
    return user


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Get a specific user by id.
    """
    user = session.get(User, user_id)
    if user == current_user:
        logger.info("User retrieved own account user_id=%s", user_id)
        return user
    if not current_user.is_superuser:
        logger.warning("User lookup denied requested_user_id=%s user_id=%s", user_id, current_user.id)
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    if user is None:
        logger.warning("User lookup failed because the user was not found requested_user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("User retrieved by administrator requested_user_id=%s administrator_id=%s", user_id, current_user.id)
    return user


@router.patch("/{user_id}", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic)
def update_user(*, session: SessionDep, user_id: uuid.UUID, user_in: UserUpdate) -> Any:
    """
    Update a user.
    """

    db_user = session.get(User, user_id)
    if not db_user:
        logger.warning("User update failed because the user was not found user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="The user with this id does not exist in the system")
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            logger.warning("User update rejected because the email is already registered user_id=%s existing_user_id=%s", user_id, existing_user.id)
            raise HTTPException(status_code=409, detail="User with this email already exists")

    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    logger.info("User updated by administrator user_id=%s", user_id)
    return db_user


@router.delete("/{user_id}", dependencies=[Depends(get_current_active_superuser)])
def delete_user(session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        logger.warning("User deletion failed because the user was not found user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        logger.warning("Administrator self-deletion rejected user_id=%s", current_user.id)
        raise HTTPException(status_code=403, detail="Super users are not allowed to delete themselves")
    session.delete(user)
    session.commit()
    logger.info("User deleted by administrator user_id=%s administrator_id=%s", user_id, current_user.id)
    return Message(message="User deleted successfully")
