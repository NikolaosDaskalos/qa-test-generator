"""Test the GitHub Pull Request failure-stage migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0002_github_pull_request_failure_stage.py"
    spec = importlib.util.spec_from_file_location("github_pull_request_failure_stage_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_github_pull_request_failure_stage(monkeypatch) -> None:
    migration = _migration()
    executed = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(execute=lambda statement: executed.append(str(statement))))

    migration.upgrade()

    assert "ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS 'github_pull_request'" in " ".join(executed)


def test_migration_follows_the_initial_schema() -> None:
    migration = _migration()
    assert migration.down_revision == "0001_initial_schema"
