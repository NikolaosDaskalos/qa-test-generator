"""Persist the generated Test Patch on a Coding Run.

Adds the generation branch, canonical diff, generated file proposals, and
collected External References produced by the test-generation path.

Revision ID: 0008_coding_run_patch
Revises: 0007_coding_run
Create Date: 2026-06-16 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_coding_run_patch"
down_revision = "0007_coding_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coding_run", sa.Column("generation_branch", sa.String(length=255), nullable=True))
    op.add_column("coding_run", sa.Column("diff", sa.Text(), nullable=True))
    op.add_column("coding_run", sa.Column("generated_files", sa.JSON(), nullable=True))
    op.add_column("coding_run", sa.Column("external_references", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("coding_run", "external_references")
    op.drop_column("coding_run", "generated_files")
    op.drop_column("coding_run", "diff")
    op.drop_column("coding_run", "generation_branch")
