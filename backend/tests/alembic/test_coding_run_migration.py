"""Test the Coding Run table migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, ForeignKeyConstraint, UniqueConstraint


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0007_coding_run.py"
    spec = importlib.util.spec_from_file_location("coding_run_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_creates_coding_run_with_ownership_and_failure_columns(monkeypatch) -> None:
    migration = _migration()
    created_tables = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda *args: created_tables.append(args),
            create_index=lambda *args, **kwargs: None,
            f=lambda name: name,
        ),
    )

    migration.upgrade()

    tables = {items[0]: items[1:] for items in created_tables}
    assert "coding_run" in tables
    columns = {item.name: item for item in tables["coding_run"] if isinstance(item, Column)}
    foreign_keys = [item for item in tables["coding_run"] if isinstance(item, ForeignKeyConstraint)]
    unique_constraints = [item for item in tables["coding_run"] if isinstance(item, UniqueConstraint)]

    assert columns["repository_session_id"].nullable is False
    assert "repository_id" not in columns
    assert columns["status"].nullable is False
    assert columns["thread_id"].nullable is False
    assert columns["failed_stage"].nullable is True
    assert columns["failure_reason"].nullable is True
    assert columns["revision_count"].nullable is False
    assert all(foreign_key.ondelete == "CASCADE" for foreign_key in foreign_keys)
    assert len(foreign_keys) == 1
    assert any(constraint.name == "uq_coding_run_thread_id" for constraint in unique_constraints)
