"""Replace Search Sessions with Repository Sessions and Session History.

Revision ID: 0004_repository_sessions
Revises: 0003_source_document
Create Date: 2026-06-13 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_repository_sessions"
down_revision = "0003_source_document"
branch_labels = None
depends_on = None

session_message_role = sa.Enum("user", "assistant", name="sessionmessagerole")


def upgrade() -> None:
    op.create_table(
        "repository_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["repository_id"], ["repository.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_repository_session_owner_id"),
        "repository_session",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_repository_session_repository_id"),
        "repository_session",
        ["repository_id"],
        unique=False,
    )

    op.create_table(
        "session_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", session_message_role, nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 1", name="ck_session_history_position"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["repository_session.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "position", name="uq_session_history_position"
        ),
    )
    op.create_index(
        op.f("ix_session_history_session_id"),
        "session_history",
        ["session_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION prevent_repository_session_repository_change()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.repository_id IS DISTINCT FROM OLD.repository_id THEN
                RAISE EXCEPTION 'Repository Session binding is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER repository_session_repository_immutable
        BEFORE UPDATE OF repository_id ON repository_session
        FOR EACH ROW
        EXECUTE FUNCTION prevent_repository_session_repository_change()
        """
    )

    # Legacy Search Sessions have no Repository identity and cannot be mapped safely.
    op.drop_table("search_history")
    op.drop_table("search_session")


def downgrade() -> None:
    op.create_table(
        "search_session",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("memory", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "search_history",
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["search_session.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        "DROP TRIGGER repository_session_repository_immutable ON repository_session"
    )
    op.execute("DROP FUNCTION prevent_repository_session_repository_change()")
    op.drop_index(
        op.f("ix_session_history_session_id"), table_name="session_history"
    )
    op.drop_table("session_history")
    op.drop_index(
        op.f("ix_repository_session_repository_id"),
        table_name="repository_session",
    )
    op.drop_index(
        op.f("ix_repository_session_owner_id"), table_name="repository_session"
    )
    op.drop_table("repository_session")
    session_message_role.drop(op.get_bind(), checkfirst=True)
