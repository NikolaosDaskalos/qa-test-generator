"""Relational database: engine, seeding, records, and persistence adapters.

The engine and seeding form the shared session setup; ``models`` holds the
SQLModel records and ``persistence`` the adapters that read and write them.
"""

from app.db.seed import init_db
from app.db.session import engine

__all__ = ["engine", "init_db"]
