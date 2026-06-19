"""Test the data-preserving Repository Document rename."""

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration():
    migration_path = Path(__file__).resolve().parents[2] / "app/alembic/versions/0013_repository_document.py"
    spec = importlib.util.spec_from_file_location("repository_document_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_renames_the_table_without_losing_existing_documents(monkeypatch) -> None:
    engine = sa.create_engine("sqlite://")
    document_id = uuid.uuid4()
    repository_id = uuid.uuid4()

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE source_document ("
                "id VARCHAR(36) PRIMARY KEY, repository_id VARCHAR(36) NOT NULL, "
                "content TEXT NOT NULL, doc_metadata TEXT)"
            )
        )
        connection.execute(sa.text("CREATE INDEX ix_source_document_repository_id ON source_document (repository_id)"))
        connection.execute(
            sa.text(
                "INSERT INTO source_document (id, repository_id, content, doc_metadata) "
                "VALUES (:id, :repository_id, :content, :metadata)"
            ),
            {"id": str(document_id), "repository_id": str(repository_id), "content": "def answer(): return 42", "metadata": '{"source":"app/core.py"}'},
        )

        migration = _migration()
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()

        assert sa.inspect(connection).has_table("repository_document")
        assert not sa.inspect(connection).has_table("source_document")
        row = connection.execute(sa.text("SELECT id, repository_id, content, doc_metadata FROM repository_document")).one()
        assert row == (str(document_id), str(repository_id), "def answer(): return 42", '{"source":"app/core.py"}')

