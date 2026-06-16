"""Record Approval and Git publication failure stages.

Adds the ``approved`` lifecycle status a Coding Run transitions into after its
reviewed Test Patch is committed and pushed. Also adds ``git_commit`` and
``git_push`` failure stages so Approval failures remain distinguishable from
generation and review failures.

Revision ID: 0011_coding_run_approval
Revises: 0010_coding_run_rejected
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op

revision = "0011_coding_run_approval"
down_revision = "0010_coding_run_rejected"
branch_labels = None
depends_on = None

NEW_STATUS_VALUES = ("approved",)
NEW_STAGE_VALUES = ("git_commit", "git_push")


def upgrade() -> None:
    # New PostgreSQL enum values must be added outside a transaction block.
    for value in NEW_STATUS_VALUES:
        op.execute(f"ALTER TYPE codingrunstatus ADD VALUE IF NOT EXISTS '{value}'")
    for value in NEW_STAGE_VALUES:
        op.execute(f"ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot drop individual enum values, so these additions are irreversible.
    pass
