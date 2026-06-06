"""Add git repository models and timezone-aware search timestamps.

Revision ID: 0002_add_git_repository_models
Revises: 0001_initial_schema
Create Date: 2026-06-06 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0002_add_git_repository_models"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


git_repository_provider = sa.Enum(
    "github",
    "gitlab",
    "bitbucket",
    "other",
    name="gitrepositoryprovider",
)
git_repository_status = sa.Enum(
    "pending",
    "cloning",
    "ready",
    "failed",
    "archived",
    name="gitrepositorystatus",
)


def upgrade() -> None:
    op.create_table(
        "git_repository",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("provider", git_repository_provider, nullable=False),
        sa.Column("repository_owner", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", git_repository_status, nullable=False),
        sa.Column("hashed_token", sa.String(), nullable=True),
        sa.Column(
            "token_expiration_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("local_path", sa.String(length=4096), nullable=True),
        sa.Column("last_cloned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "repository_url",
            name="uq_repository_owner_url",
        ),
    )
    op.create_index(
        op.f("ix_git_repository_name"),
        "git_repository",
        ["name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_git_repository_status"),
        "git_repository",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_git_repository_user_id"),
        "git_repository",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "branch",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("git_repository_id", sa.Uuid(), nullable=False),
        sa.Column("local_head_sha", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["git_repository_id"],
            ["git_repository.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "git_repository_id",
            "name",
            name="uq_git_repository_branch_name",
        ),
    )
    op.create_index(
        op.f("ix_branch_git_repository_id"),
        "branch",
        ["git_repository_id"],
        unique=False,
    )

    op.alter_column(
        "search_session",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "search_session",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "search_history",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "search_history",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "search_session",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "search_session",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.drop_index(op.f("ix_branch_git_repository_id"), table_name="branch")
    op.drop_table("branch")
    op.drop_index(op.f("ix_git_repository_user_id"), table_name="git_repository")
    op.drop_index(op.f("ix_git_repository_status"), table_name="git_repository")
    op.drop_index(op.f("ix_git_repository_name"), table_name="git_repository")
    op.drop_table("git_repository")

    bind = op.get_bind()
    git_repository_status.drop(bind, checkfirst=True)
    git_repository_provider.drop(bind, checkfirst=True)
