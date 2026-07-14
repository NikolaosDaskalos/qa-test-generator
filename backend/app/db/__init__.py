"""Relational database: engine, seeding, records, and persistence adapters.

The engine and seeding form the shared session setup; ``models`` holds the
SQLModel records and ``persistence`` the adapters that read and write them.
"""

from typing import TYPE_CHECKING, Any

from app.db.session import engine

if TYPE_CHECKING:
    from app.db.seed import init_db

__all__ = ["engine", "init_db"]


def __getattr__(name: str) -> Any:
    """Load ``init_db`` lazily so importing ``app.db`` (via any model) does not eagerly pull
    ``app.db.seed`` → ``app.db.persistence.user_store`` → ``app.schemas``. That eager chain forms a circular import
    whenever ``app.schemas`` is imported before ``app.db``; deferring it keeps ``app.db`` importable
    from any order while ``from app.db import init_db`` still works for the seeding scripts.
    """
    if name == "init_db":
        from app.db.seed import init_db

        return init_db
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
