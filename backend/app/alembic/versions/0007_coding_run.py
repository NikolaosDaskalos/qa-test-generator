"""Add the Coding Run table for Test-Generation Tasks.

Revision ID: 0007_coding_run
Revises: 0006_session_history_citations
Create Date: 2026-06-15 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_coding_run"
down_revision = "0006_session_history_citations"
branch_labels = None
depends_on = None

coding_run_status = sa.Enum(
    "queued", "planning", "retrieving", "generating", "awaiting_review", "succeeded", "failed", name="codingrunstatus"
)
coding_run_stage = sa.Enum("planning", "retrieving", "generating", name="codingrunstage")


def upgrade() -> None:
    op.create_table(
        "coding_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_session_id", sa.Uuid(), nullable=False),
        sa.Column("status", coding_run_status, nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("failed_stage", coding_run_stage, nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_count >= 0", name="ck_coding_run_revision_count"),
        sa.ForeignKeyConstraint(["repository_session_id"], ["repository_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", name="uq_coding_run_thread_id"),
    )
    op.create_index(op.f("ix_coding_run_repository_session_id"), "coding_run", ["repository_session_id"], unique=False)
    op.create_index(op.f("ix_coding_run_status"), "coding_run", ["status"], unique=False)
    op.create_index(op.f("ix_coding_run_thread_id"), "coding_run", ["thread_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_coding_run_thread_id"), table_name="coding_run")
    op.drop_index(op.f("ix_coding_run_status"), table_name="coding_run")
    op.drop_index(op.f("ix_coding_run_repository_session_id"), table_name="coding_run")
    op.drop_table("coding_run")
    coding_run_stage.drop(op.get_bind(), checkfirst=True)
    coding_run_status.drop(op.get_bind(), checkfirst=True)
