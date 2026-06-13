"""Add persisted source documents.

Revision ID: 0003_source_document
Revises: 0002_repo_indexed_commit
Create Date: 2026-06-12 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_source_document"
down_revision = "0002_repo_indexed_commit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("doc_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repository.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_source_document_repository_id"), "source_document", ["repository_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_source_document_repository_id"), table_name="source_document")
    op.drop_table("source_document")
