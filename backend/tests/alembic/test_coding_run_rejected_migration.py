"""Test the Coding Run rejection migration (new ``rejected`` status value)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0010_coding_run_rejected.py"
    spec = importlib.util.spec_from_file_location("coding_run_rejected_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_the_rejected_status_value(monkeypatch) -> None:
    migration = _migration()
    executed = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=lambda statement: executed.append(str(statement))))

    migration.upgrade()

    assert "ALTER TYPE codingrunstatus ADD VALUE IF NOT EXISTS 'rejected'" in " ".join(executed)


def test_migration_follows_the_review_migration() -> None:
    migration = _migration()
    assert migration.down_revision == "0009_coding_run_review"
