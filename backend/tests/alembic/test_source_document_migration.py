"""Test the source-document schema migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0003_source_document.py"
    spec = importlib.util.spec_from_file_location("source_document_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_creates_source_document_table_and_repository_index(monkeypatch) -> None:
    migration = _migration()
    created_tables = []
    created_indexes = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            create_table=lambda *args: created_tables.append(args),
            create_index=lambda *args, **kwargs: created_indexes.append((args, kwargs)),
            f=lambda name: name,
        ),
    )

    migration.upgrade()

    table_name, *items = created_tables[0]
    columns = {item.name: item for item in items if isinstance(item, Column)}
    assert table_name == "source_document"
    assert set(columns) == {"id", "repository_id", "content", "doc_metadata", "created_at", "updated_at"}
    assert columns["content"].nullable is False
    assert created_indexes == [(("ix_source_document_repository_id", "source_document", ["repository_id"]), {"unique": False})]


def test_downgrade_drops_index_before_table(monkeypatch) -> None:
    migration = _migration()
    calls = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            drop_index=lambda *args, **kwargs: calls.append(("index", args, kwargs)),
            drop_table=lambda *args, **kwargs: calls.append(("table", args, kwargs)),
            f=lambda name: name,
        ),
    )

    migration.downgrade()

    assert [call[0] for call in calls] == ["index", "table"]
