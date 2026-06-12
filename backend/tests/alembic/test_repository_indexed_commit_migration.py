"""Test the Repository indexed-commit migration contract."""

import importlib.util
from pathlib import Path


def _migration_module():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0002_repository_indexed_commit_sha.py"
    spec = importlib.util.spec_from_file_location("repository_indexed_commit_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_and_removes_nullable_sha_column(monkeypatch) -> None:
    migration = _migration_module()
    added_columns = []
    dropped_columns = []
    monkeypatch.setattr(migration.op, "add_column", lambda table, column: added_columns.append((table, column)))
    monkeypatch.setattr(migration.op, "drop_column", lambda table, column: dropped_columns.append((table, column)))

    migration.upgrade()
    migration.downgrade()

    table, column = added_columns[0]
    assert table == "repository"
    assert column.name == "indexed_commit_sha"
    assert column.nullable
    assert column.type.length == 40
    assert dropped_columns == [("repository", "indexed_commit_sha")]
