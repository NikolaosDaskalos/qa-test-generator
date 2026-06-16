"""Persist Patch Review on a Coding Run.

Adds the review findings column and the new lifecycle status values the review
stage transitions into: ``reviewing`` while the patch is assessed, then
``awaiting_approval`` on an accepted review or ``changes_requested`` on a
rejected one. Also adds the ``reviewing`` failure stage so a reviewer that
raises is recorded as a reviewing-stage Run Failure rather than leaving the run
stuck in ``reviewing``.

Revision ID: 0009_coding_run_review
Revises: 0008_coding_run_patch
Create Date: 2026-06-16 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_coding_run_review"
down_revision = "0008_coding_run_patch"
branch_labels = None
depends_on = None

NEW_STATUS_VALUES = ("reviewing", "awaiting_approval", "changes_requested")
NEW_STAGE_VALUES = ("reviewing",)


def upgrade() -> None:
    # New PostgreSQL enum values must be added outside a transaction block.
    for value in NEW_STATUS_VALUES:
        op.execute(f"ALTER TYPE codingrunstatus ADD VALUE IF NOT EXISTS '{value}'")
    for value in NEW_STAGE_VALUES:
        op.execute(f"ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("coding_run", sa.Column("review_findings", sa.JSON(), nullable=True))


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value, so only the column is reversed.
    op.drop_column("coding_run", "review_findings")
