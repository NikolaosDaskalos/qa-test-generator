"""Test FastAPI startup and shutdown resource handling."""

import asyncio

import pytest

from app import main


def test_lifespan_initializes_and_closes_weaviate_and_checkpointer(monkeypatch) -> None:
    """Initialize Weaviate and the graph checkpointer before serving; close both afterward."""
    events = []
    sentinel_pool = object()
    monkeypatch.setattr(main.vector_db, "initialize_weaviate", lambda: events.append("weaviate_initialized"))
    monkeypatch.setattr(main.vector_db, "close_weaviate", lambda: events.append("weaviate_closed"))
    monkeypatch.setattr(main, "open_checkpointer", lambda: (events.append("checkpointer_opened") or ("saver", sentinel_pool)))
    monkeypatch.setattr(main, "close_checkpointer", lambda pool: events.append("checkpointer_closed") if pool is sentinel_pool else events.append("wrong_pool"))

    async def run_lifespan():
        """Run the application lifespan while recording the active phase."""
        async with main.lifespan(main.app):
            events.append("running")
            assert main.app.state.session_checkpointer == "saver"

    asyncio.run(run_lifespan())

    assert events == ["weaviate_initialized", "checkpointer_opened", "running", "checkpointer_closed", "weaviate_closed"]


def test_lifespan_propagates_startup_failure(monkeypatch) -> None:
    """Propagate Weaviate initialization failures from startup."""

    def fail_initialization():
        """Simulate an unavailable Weaviate service."""
        raise RuntimeError("Weaviate unavailable")

    monkeypatch.setattr(main.vector_db, "initialize_weaviate", fail_initialization)
    monkeypatch.setattr(main, "open_checkpointer", lambda: (_ for _ in ()).throw(AssertionError("checkpointer must not open if Weaviate init fails")))

    async def run_lifespan():
        """Enter the application lifespan under test."""
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="Weaviate unavailable"):
        asyncio.run(run_lifespan())
