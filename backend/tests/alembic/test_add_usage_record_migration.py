"""Test the Usage Record Alembic migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0002_add_usage_record.py"
    spec = importlib.util.spec_from_file_location("add_usage_record_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_tables():
    migration = _migration()
    created_tables = []
    dropped_tables = []
    migration.op = SimpleNamespace(
        create_table=lambda *args: created_tables.append(args),
        create_index=lambda *a, **k: None,
        drop_table=lambda name: dropped_tables.append(name),
        drop_index=lambda *a, **k: None,
        f=lambda name: name,
    )
    return migration, created_tables, dropped_tables


def test_usage_record_migration_chains_onto_the_initial_schema() -> None:
    migration = _migration()

    assert migration.revision == "0002_add_usage_record"
    assert migration.down_revision == "0001_initial_schema"


def test_upgrade_creates_the_usage_record_columns() -> None:
    migration, created_tables, _ = _upgrade_tables()

    migration.upgrade()

    tables = {items[0]: items[1:] for items in created_tables}
    columns = {item.name: item for item in tables["usage_record"] if isinstance(item, Column)}

    assert columns["cost"].nullable is True
    assert columns["session_history_id"].nullable is True
    assert columns["coding_run_id"].nullable is True
    assert columns["user_id"].nullable is False
    assert columns["repository_id"].nullable is False
    assert columns["repository_session_id"].nullable is False


def test_downgrade_drops_the_usage_record_table() -> None:
    migration, _, dropped_tables = _upgrade_tables()

    migration.downgrade()

    assert dropped_tables == ["usage_record"]
