"""Add github_pull_request to Coding Run failure stages.

Revision ID: 0002_github_pull_request_failure_stage
Revises: 0001_initial_schema
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op

revision = "0002_github_pull_request_failure_stage"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE codingrunstage ADD VALUE IF NOT EXISTS 'github_pull_request'")


def downgrade() -> None:
    pass
