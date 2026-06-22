"""Test removal of the item and todo tables."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, ForeignKeyConstraint


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0005_remove_items_and_todos.py"
    spec = importlib.util.spec_from_file_location("remove_items_and_todos_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_drops_todo_and_item_tables(monkeypatch) -> None:
    migration = _migration()
    dropped_tables = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(drop_table=lambda table: dropped_tables.append(table)))

    migration.upgrade()

    assert dropped_tables == ["todo", "item"]


def test_downgrade_restores_owned_item_and_todo_tables(monkeypatch) -> None:
    migration = _migration()
    created_tables = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(create_table=lambda *args: created_tables.append(args)))

    migration.downgrade()

    tables = {items[0]: items[1:] for items in created_tables}
    assert set(tables) == {"item", "todo"}

    for table_items in tables.values():
        columns = {item.name: item for item in table_items if isinstance(item, Column)}
        foreign_keys = [item for item in table_items if isinstance(item, ForeignKeyConstraint)]
        assert columns["user_id"].nullable is False
        assert len(foreign_keys) == 1
        assert foreign_keys[0].ondelete == "CASCADE"
