"""The process-wide durable checkpointer for the unified session graph.

The graph's in-flight state (the ``messages`` spine and routing channels) is
persisted by a ``PostgresSaver`` keyed on the per-run ``thread_id`` — distinct
from the durable ``Coding Run`` domain record, which owns ownership, status,
failure, and revision count. The connection pool is the singleton: it is opened
once in the FastAPI lifespan (where ``setup()`` provisions the checkpoint tables)
and shared across requests, while compiling the graph itself stays per request.
"""

import logging

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# psycopg requires autocommit for the checkpointer's writes, and pipelined
# prepared statements must be disabled for pooled connections.
_CONNECTION_KWARGS = {"autocommit": True, "prepare_threshold": 0}


def _conninfo() -> str:
    """Render the app's SQLAlchemy URL as a libpq conninfo string psycopg accepts."""
    return str(settings.SQLALCHEMY_DATABASE_URI).replace("postgresql+psycopg://", "postgresql://")


def open_checkpointer() -> tuple[PostgresSaver, ConnectionPool]:
    """Open the shared connection pool and provision the checkpoint tables.

    Returns the ``PostgresSaver`` to compile graphs against and the pool to close
    at shutdown. ``setup()`` is idempotent, so re-running it at startup is safe.
    """
    pool = ConnectionPool(
        conninfo=_conninfo(),
        max_size=settings.CHECKPOINTER_POOL_MAX_SIZE,
        kwargs=_CONNECTION_KWARGS,
        open=True,
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    logger.info(
        "Session graph checkpointer initialized with pool_max_size=%s",
        settings.CHECKPOINTER_POOL_MAX_SIZE,
    )
    return checkpointer, pool


def close_checkpointer(pool: ConnectionPool) -> None:
    """Close the shared checkpointer connection pool during shutdown."""
    pool.close()
    logger.info("Session graph checkpointer connection pool closed")
