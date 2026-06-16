"""Test the Coding Run review migration (findings column + new status values)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0009_coding_run_review.py"
    spec = importlib.util.spec_from_file_location("coding_run_review_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_review_findings_column_and_new_status_values(monkeypatch) -> None:
    migration = _migration()
    added_columns = []
    executed = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            add_column=lambda table, column: added_columns.append((table, column)),
            execute=lambda statement: executed.append(str(statement)),
        ),
    )

    migration.upgrade()

    columns = {column.name: column for _table, column in added_columns if isinstance(column, Column)}
    assert "review_findings" in columns
    assert columns["review_findings"].nullable is True
    statements = " ".join(executed)
    for value in ("reviewing", "awaiting_approval", "changes_requested"):
        assert value in statements
    # The reviewing failure stage is added so a reviewer that raises is recorded as
    # a reviewing-stage Run Failure rather than leaving the run stuck in reviewing.
    assert "ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS 'reviewing'" in statements
