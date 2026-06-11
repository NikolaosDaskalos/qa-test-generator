"""Add the Repository indexed commit SHA.

Revision ID: 0002_repo_indexed_commit
Revises: 0001_initial_schema
Create Date: 2026-06-11 23:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_repo_indexed_commit"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repository", sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("repository", "indexed_commit_sha")
