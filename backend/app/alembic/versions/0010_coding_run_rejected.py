"""Record an owner's rejection of a reviewed Test Patch.

Adds the ``rejected`` lifecycle status a Coding Run transitions into when its
owner rejects the reviewed patch through the human-in-the-loop decision: the
generated changes are discarded and the temporary branch removed, while the
persisted review record is preserved. No new column is needed — the rejection is
a status transition only.

Revision ID: 0010_coding_run_rejected
Revises: 0009_coding_run_review
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op

revision = "0010_coding_run_rejected"
down_revision = "0009_coding_run_review"
branch_labels = None
depends_on = None

NEW_STATUS_VALUES = ("rejected",)


def upgrade() -> None:
    # New PostgreSQL enum values must be added outside a transaction block.
    for value in NEW_STATUS_VALUES:
        op.execute(f"ALTER TYPE codingrunstatus ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot drop a single enum value, so the rejected status is irreversible.
    pass
