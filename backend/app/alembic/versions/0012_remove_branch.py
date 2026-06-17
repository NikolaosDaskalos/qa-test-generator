"""Remove unused branch table.

Revision ID: 0012_remove_branch
Revises: 0011_coding_run_approval
Create Date: 2026-06-17 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_remove_branch"
down_revision = "0011_coding_run_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_branch_repository_id"), table_name="branch")
    op.drop_table("branch")


def downgrade() -> None:
    op.create_table(
        "branch",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("local_head_sha", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repository.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "name", name="uq_repository_branch_name"),
    )
    op.create_index(op.f("ix_branch_repository_id"), "branch", ["repository_id"], unique=False)
