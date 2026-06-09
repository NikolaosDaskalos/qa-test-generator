"""Test FastAPI startup and shutdown resource handling."""

import asyncio

import pytest

from app import main


def test_lifespan_initializes_and_closes_weaviate(monkeypatch) -> None:
    """Initialize before serving and close resources afterward."""
    events = []
    monkeypatch.setattr(main.weaviate_init, "initialize_weaviate", lambda: events.append("initialized"))
    monkeypatch.setattr(main.weaviate_init, "close_weaviate", lambda: events.append("closed"))

    async def run_lifespan():
        """Run the application lifespan while recording the active phase."""
        async with main.lifespan(main.app):
            events.append("running")

    asyncio.run(run_lifespan())

    assert events == ["initialized", "running", "closed"]


def test_lifespan_propagates_startup_failure(monkeypatch) -> None:
    """Propagate Weaviate initialization failures from startup."""

    def fail_initialization():
        """Simulate an unavailable Weaviate service."""
        raise RuntimeError("Weaviate unavailable")

    monkeypatch.setattr(main.weaviate_init, "initialize_weaviate", fail_initialization)

    async def run_lifespan():
        """Enter the application lifespan under test."""
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="Weaviate unavailable"):
        asyncio.run(run_lifespan())
