"""Align git repository persistence with the background processing pipeline.

Revision ID: 0003_git_repository_pipeline
Revises: 0002_add_git_repository_models
Create Date: 2026-06-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_git_repository_pipeline"
down_revision = "0002_add_git_repository_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE gitrepositorystatus ADD VALUE IF NOT EXISTS 'cloned'")
    op.execute("ALTER TYPE gitrepositorystatus ADD VALUE IF NOT EXISTS 'indexing'")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'git_repository'
                  AND column_name = 'hashed_token'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'git_repository'
                  AND column_name = 'encrypted_token'
            ) THEN
                ALTER TABLE git_repository
                RENAME COLUMN hashed_token TO encrypted_token;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE git_repository
        ADD COLUMN IF NOT EXISTS encrypted_token VARCHAR(4096)
        """
    )
    op.execute(
        """
        ALTER TABLE git_repository
        ALTER COLUMN encrypted_token TYPE VARCHAR(4096)
        """
    )
    op.execute(
        """
        ALTER TABLE git_repository
        ADD COLUMN IF NOT EXISTS token_expiration_date TIMESTAMPTZ
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'git_repository'
                  AND column_name = 'repository_owner'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'git_repository'
                  AND column_name = 'owner'
            ) THEN
                ALTER TABLE git_repository
                RENAME COLUMN repository_owner TO owner;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'git_repository'
                  AND column_name = 'last_error'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'git_repository'
                  AND column_name = 'failed_reason'
            ) THEN
                ALTER TABLE git_repository
                RENAME COLUMN last_error TO failed_reason;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        "ALTER TABLE git_repository DROP COLUMN IF EXISTS last_cloned_at"
    )
    op.execute(
        """
        ALTER TABLE git_repository
        DROP CONSTRAINT IF EXISTS uq_repository_owner_url
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_user_id_repository_url'
            ) THEN
                ALTER TABLE git_repository
                ADD CONSTRAINT uq_user_id_repository_url
                UNIQUE (user_id, repository_url);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_id_repository_url",
        "git_repository",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_repository_owner_url",
        "git_repository",
        ["user_id", "repository_url"],
    )
    op.add_column(
        "git_repository",
        sa.Column("last_cloned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "git_repository",
        "failed_reason",
        new_column_name="last_error",
        existing_type=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "git_repository",
        "owner",
        new_column_name="repository_owner",
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "git_repository",
        "encrypted_token",
        new_column_name="hashed_token",
        existing_type=sa.String(length=4096),
        type_=sa.String(),
        existing_nullable=True,
        nullable=True,
    )
