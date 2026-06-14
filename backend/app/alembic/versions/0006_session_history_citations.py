"""Add structural citations to session history.

Revision ID: 0006_session_history_citations
Revises: 0005_remove_items_todos
Create Date: 2026-06-14 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_session_history_citations"
down_revision = "0005_remove_items_todos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Citations are retained structurally on each assistant message instead of being rendered
    # into a Markdown footer. The server default backfills existing rows with an empty list.
    op.add_column(
        "session_history",
        sa.Column("citations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("session_history", "citations")
