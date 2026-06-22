"""Seed the relational database with required initial data."""

import logging

from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.db.models import User
from app.schemas import UserCreate

logger = logging.getLogger(__name__)


def init_db(session: Session) -> None:
    """Ensure the first superuser exists, creating it from settings if absent."""
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # SQLModel.metadata.create_all(engine)

    user = session.exec(select(User).where(User.email == settings.FIRST_SUPERUSER)).first()
    if not user:
        logger.info("Creating initial superuser")
        user_in = UserCreate(email=settings.FIRST_SUPERUSER, password=settings.FIRST_SUPERUSER_PASSWORD, is_superuser=True)
        user = crud.create_user(session=session, user_create=user_in)
        logger.info("Initial superuser created user_id=%s", user.id)
    else:
        logger.info("Initial superuser already exists user_id=%s", user.id)
