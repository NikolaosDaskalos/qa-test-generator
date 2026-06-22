"""Test the Repository Session schema replacement migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, ForeignKeyConstraint


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0004_repository_sessions.py"
    spec = importlib.util.spec_from_file_location("repository_session_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_replaces_search_memory_with_bound_sessions_and_message_history(monkeypatch) -> None:
    migration = _migration()
    created_tables = []
    dropped_tables = []
    executed_sql = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda *args: created_tables.append(args),
            create_index=lambda *args, **kwargs: None,
            drop_table=lambda table: dropped_tables.append(table),
            execute=lambda sql: executed_sql.append(str(sql)),
            f=lambda name: name,
        ),
    )

    migration.upgrade()

    tables = {items[0]: items[1:] for items in created_tables}
    session_columns = {item.name: item for item in tables["repository_session"] if isinstance(item, Column)}
    history_columns = {item.name: item for item in tables["session_history"] if isinstance(item, Column)}
    session_foreign_keys = [item for item in tables["repository_session"] if isinstance(item, ForeignKeyConstraint)]
    history_foreign_keys = [item for item in tables["session_history"] if isinstance(item, ForeignKeyConstraint)]

    assert session_columns["repository_id"].nullable is False
    assert session_columns["user_id"].nullable is False
    assert "memory" not in session_columns
    assert history_columns["session_id"].nullable is False
    assert history_columns["role"].nullable is False
    assert history_columns["content"].nullable is False
    assert all(foreign_key.ondelete == "CASCADE" for foreign_key in session_foreign_keys)
    assert all(foreign_key.ondelete == "CASCADE" for foreign_key in history_foreign_keys)
    assert dropped_tables == ["search_history", "search_session"]
    assert any("prevent_repository_session_repository_change" in sql for sql in executed_sql)
