"""Test the Coding Run Approval migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0011_coding_run_approval.py"
    spec = importlib.util.spec_from_file_location("coding_run_approval_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_approval_status_and_git_failure_stages(monkeypatch) -> None:
    migration = _migration()
    executed = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=lambda statement: executed.append(str(statement))))

    migration.upgrade()

    statements = " ".join(executed)
    assert "ALTER TYPE codingrunstatus ADD VALUE IF NOT EXISTS 'approved'" in statements
    assert "ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS 'git_commit'" in statements
    assert "ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS 'git_push'" in statements


def test_migration_follows_the_rejection_migration() -> None:
    migration = _migration()
    assert migration.down_revision == "0010_coding_run_rejected"
