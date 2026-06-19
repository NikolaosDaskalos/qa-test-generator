"""Authentication routes: access-token login, token testing, and password recovery/reset."""

import logging
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm

from app import crud
from app.core import security, settings
from app.dependencies import CurrentUser, SessionDep, get_current_active_superuser
from app.schemas import UserPublic, UserUpdate
from app.schemas.authentication import Message, NewPassword, Token
from app.utils import generate_password_reset_token, generate_reset_password_email, send_email, verify_password_reset_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["login"])


@router.post("/login/access-token")
def login_access_token(session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = crud.authenticate(session=session, email=form_data.username, password=form_data.password)
    if not user:
        logger.warning("Login rejected because credentials are incorrect")
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        logger.warning("Login rejected because the user is inactive user_id=%s", user.id)
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    logger.info("Login succeeded user_id=%s", user.id)
    return Token(access_token=security.create_access_token(user.id, expires_delta=access_token_expires))


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


@router.post("/password-recovery/{email}")
def recover_password(email: str, session: SessionDep) -> Message:
    """
    Password Recovery
    """
    user = crud.get_user_by_email(session=session, email=email)

    # Always return the same response to prevent email enumeration attacks
    # Only send email if user actually exists
    if user:
        logger.info("Password recovery email requested for registered user_id=%s", user.id)
        password_reset_token = generate_password_reset_token(email=email)
        email_data = generate_reset_password_email(email_to=user.email, email=email, token=password_reset_token)
        send_email(email_to=user.email, subject=email_data.subject, html_content=email_data.html_content)
    else:
        logger.warning("Password recovery requested for an unregistered email")
    return Message(message="If that email is registered, we sent a password recovery link")


@router.post("/reset-password/")
def reset_password(session: SessionDep, body: NewPassword) -> Message:
    """
    Reset password
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        logger.warning("Password reset rejected because the token is invalid")
        raise HTTPException(status_code=400, detail="Invalid token")
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        # Don't reveal that the user doesn't exist - use same error as invalid token
        logger.warning("Password reset rejected because the token user was not found")
        raise HTTPException(status_code=400, detail="Invalid token")
    elif not user.is_active:
        logger.warning("Password reset rejected because the user is inactive user_id=%s", user.id)
        raise HTTPException(status_code=400, detail="Inactive user")
    user_in_update = UserUpdate(password=body.new_password)
    crud.update_user(session=session, db_user=user, user_in=user_in_update)
    logger.info("Password reset completed user_id=%s", user.id)
    return Message(message="Password updated successfully")


@router.post("/password-recovery-html-content/{email}", dependencies=[Depends(get_current_active_superuser)], response_class=HTMLResponse)
def recover_password_html_content(email: str, session: SessionDep) -> Any:
    """
    HTML Content for Password Recovery
    """
    user = crud.get_user_by_email(session=session, email=email)

    if not user:
        logger.warning("Password recovery preview failed because the user was not found")
        raise HTTPException(status_code=404, detail="The user with this username does not exist in the system.")
    password_reset_token = generate_password_reset_token(email=email)
    email_data = generate_reset_password_email(email_to=user.email, email=email, token=password_reset_token)
    logger.info("Password recovery email preview generated user_id=%s", user.id)

    return HTMLResponse(content=email_data.html_content, headers={"subject:": email_data.subject})
