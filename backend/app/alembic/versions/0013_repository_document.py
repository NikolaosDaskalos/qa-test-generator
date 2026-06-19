"""Rename source documents to Repository Documents.

Revision ID: 0013_repository_document
Revises: 0012_remove_branch
Create Date: 2026-06-19 00:00:00.000000
"""

from alembic import op

revision = "0013_repository_document"
down_revision = "0012_remove_branch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_source_document_repository_id"), table_name="source_document")
    op.rename_table("source_document", "repository_document")
    op.create_index(op.f("ix_repository_document_repository_id"), "repository_document", ["repository_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_repository_document_repository_id"), table_name="repository_document")
    op.rename_table("repository_document", "source_document")
    op.create_index(op.f("ix_source_document_repository_id"), "source_document", ["repository_id"], unique=False)
