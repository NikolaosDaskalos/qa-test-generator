"""Create the current application schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-03 21:40:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

git_repository_provider = sa.Enum("github", "gitlab", "bitbucket", name="gitrepositoryprovider")
git_repository_status = sa.Enum("pending", "cloning", "cloned", "indexing", "ready", "failed", name="gitrepositorystatus")


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "item",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

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
        "todo",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "git_repository",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("provider", git_repository_provider, nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", git_repository_status, nullable=False),
        sa.Column("encrypted_token", sa.String(length=4096), nullable=True),
        sa.Column("token_expiration_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_path", sa.String(length=4096), nullable=True),
        sa.Column("failed_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "repository_url", name="uq_user_id_repository_url"),
    )
    op.create_index(op.f("ix_git_repository_name"), "git_repository", ["name"], unique=False)
    op.create_index(op.f("ix_git_repository_status"), "git_repository", ["status"], unique=False)
    op.create_index(op.f("ix_git_repository_user_id"), "git_repository", ["user_id"], unique=False)

    op.create_table(
        "branch",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("git_repository_id", sa.Uuid(), nullable=False),
        sa.Column("local_head_sha", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["git_repository_id"], ["git_repository.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("git_repository_id", "name", name="uq_git_repository_branch_name"),
    )
    op.create_index(op.f("ix_branch_git_repository_id"), "branch", ["git_repository_id"], unique=False)

    op.create_table(
        "search_history",
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["search_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("branch")
    op.drop_table("git_repository")
    op.drop_table("search_history")
    op.drop_table("todo")
    op.drop_table("search_session")
    op.drop_table("item")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
    git_repository_status.drop(op.get_bind(), checkfirst=True)
    git_repository_provider.drop(op.get_bind(), checkfirst=True)
