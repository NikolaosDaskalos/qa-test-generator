"""Test the squashed Alembic baseline migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("initial_schema_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_schema_is_the_only_revision_root() -> None:
    migration = _migration()

    assert migration.revision == "0001_initial_schema"
    assert migration.down_revision is None


def test_initial_schema_contains_current_coding_run_columns() -> None:
    migration = _migration()
    created_tables = []
    migration.op = SimpleNamespace(create_table=lambda *args: created_tables.append(args), create_index=lambda *a, **k: None, f=lambda name: name)

    migration.upgrade()

    tables = {items[0]: items[1:] for items in created_tables}
    coding_run_columns = {item.name: item for item in tables["coding_run"] if isinstance(item, Column)}

    assert "github_pull_request" in coding_run_columns["failed_stage"].type.enums
    assert coding_run_columns["pull_request_url"].nullable is True
    assert coding_run_columns["pull_request_url"].type.length == 2048


def test_initial_schema_contains_current_session_history_columns() -> None:
    migration = _migration()
    created_tables = []
    migration.op = SimpleNamespace(create_table=lambda *args: created_tables.append(args), create_index=lambda *a, **k: None, f=lambda name: name)

    migration.upgrade()

    tables = {items[0]: items[1:] for items in created_tables}
    history_columns = {item.name: item for item in tables["session_history"] if isinstance(item, Column)}

    assert history_columns["coding_run_id"].nullable is True
