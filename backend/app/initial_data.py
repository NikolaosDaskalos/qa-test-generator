"""Seed the database with initial data (the first superuser) on a fresh deployment."""

import logging

from sqlmodel import Session

from app.core import engine, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    """Open a session and run the initial-data seeding."""
    with Session(engine) as session:
        init_db(session)


def main() -> None:
    """Create the initial database data."""
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
