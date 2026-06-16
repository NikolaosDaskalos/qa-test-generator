"""Tests for the process-wide graph checkpointer pool configuration."""

from app.agent import checkpointer


class _Pool:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _Saver:
    def __init__(self, pool) -> None:
        self.pool = pool
        self.was_setup = False

    def setup(self) -> None:
        self.was_setup = True


def test_checkpointer_pool_min_size_does_not_exceed_configured_max(monkeypatch) -> None:
    monkeypatch.setattr(checkpointer.settings, "CHECKPOINTER_POOL_MAX_SIZE", 2)
    monkeypatch.setattr(checkpointer, "ConnectionPool", _Pool)
    monkeypatch.setattr(checkpointer, "PostgresSaver", _Saver)

    saver, pool = checkpointer.open_checkpointer()

    assert pool.kwargs["min_size"] == 2
    assert pool.kwargs["max_size"] == 2
    assert pool.kwargs["open"] is True
    assert saver.was_setup is True


def test_checkpointer_pool_uses_default_min_size_when_max_allows_it(monkeypatch) -> None:
    monkeypatch.setattr(checkpointer.settings, "CHECKPOINTER_POOL_MAX_SIZE", 20)
    monkeypatch.setattr(checkpointer, "ConnectionPool", _Pool)
    monkeypatch.setattr(checkpointer, "PostgresSaver", _Saver)

    _saver, pool = checkpointer.open_checkpointer()

    assert pool.kwargs["min_size"] == 4
    assert pool.kwargs["max_size"] == 20
