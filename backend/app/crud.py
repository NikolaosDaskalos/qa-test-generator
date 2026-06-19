"""User persistence helpers: create, update, look up, and authenticate users."""

import logging
from typing import Any

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


def create_user(*, session: Session, user_create: UserCreate) -> User:
    """Persist a new user, hashing the plaintext password before storing it."""
    db_obj = User.model_validate(user_create, update={"hashed_password": get_password_hash(user_create.password)})
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    logger.info("User created user_id=%s", db_obj.id)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    """Apply the set fields of ``user_in`` to ``db_user``, re-hashing the password if changed."""
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    logger.info("User updated user_id=%s fields=%s", db_user.id, sorted(user_data))
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    """Return the user with this email, or ``None`` if no such user exists."""
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    """Return the user if the credentials match, else ``None``.

    Runs a verification against a dummy hash on a missing user to keep timing
    constant, and transparently upgrades a stale password hash on success.
    """
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        logger.warning("Authentication failed because the user was not found")
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        logger.warning("Authentication failed because the password did not match user_id=%s", db_user.id)
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        logger.info("User password hash upgraded user_id=%s", db_user.id)
    logger.info("Authentication succeeded user_id=%s", db_user.id)
    return db_user
