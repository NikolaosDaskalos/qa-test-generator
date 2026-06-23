"""Create the current application schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-20 08:46:23.000000
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('user',
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_superuser', sa.Boolean(), nullable=False),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    op.create_table('repository',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('repository_url', sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=False),
    sa.Column('provider', sa.Enum('github', name='repositoryprovider'), nullable=True),
    sa.Column('owner', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('default_branch', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('indexed_commit_sha', sqlmodel.sql.sqltypes.AutoString(length=40), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'cloning', 'indexing', 'ready', 'failed', name='repositorystatus'), nullable=False),
    sa.Column('encrypted_token', sqlmodel.sql.sqltypes.AutoString(length=4096), nullable=True),
    sa.Column('token_expiration_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('local_path', sqlmodel.sql.sqltypes.AutoString(length=4096), nullable=True),
    sa.Column('failed_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'repository_url', name='uq_user_id_repository_url')
    )
    op.create_index(op.f('ix_repository_name'), 'repository', ['name'], unique=False)
    op.create_index(op.f('ix_repository_status'), 'repository', ['status'], unique=False)
    op.create_index(op.f('ix_repository_user_id'), 'repository', ['user_id'], unique=False)
    op.create_table('repository_document',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('repository_id', sa.Uuid(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('doc_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repository.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_repository_document_repository_id'), 'repository_document', ['repository_id'], unique=False)
    op.create_table('repository_session',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('repository_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['repository_id'], ['repository.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_repository_session_user_id'), 'repository_session', ['user_id'], unique=False)
    op.create_index(op.f('ix_repository_session_repository_id'), 'repository_session', ['repository_id'], unique=False)
    op.create_table('coding_run',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('repository_session_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'planning', 'retrieving', 'generating', 'awaiting_review', 'reviewing', 'awaiting_approval', 'changes_requested', 'approved', 'succeeded', 'rejected', 'failed', name='codingrunstatus'), nullable=False),
    sa.Column('thread_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('failed_stage', sa.Enum('planning', 'retrieving', 'generating', 'reviewing', 'git_commit', 'git_push', 'github_pull_request', name='codingrunstage'), nullable=True),
    sa.Column('failure_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('revision_count', sa.Integer(), nullable=False),
    sa.Column('generation_branch', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('diff', sa.Text(), nullable=True),
    sa.Column('generated_files', sa.JSON(), nullable=True),
    sa.Column('external_references', sa.JSON(), nullable=True),
    sa.Column('review_findings', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['repository_session_id'], ['repository_session.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_coding_run_repository_session_id'), 'coding_run', ['repository_session_id'], unique=False)
    op.create_index(op.f('ix_coding_run_status'), 'coding_run', ['status'], unique=False)
    op.create_index(op.f('ix_coding_run_thread_id'), 'coding_run', ['thread_id'], unique=True)
    op.create_table('session_history',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.Enum('user', 'assistant', name='sessionmessagerole'), nullable=False),
    sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('citations', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['repository_session.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'position', name='uq_session_history_position')
    )
    op.create_index(op.f('ix_session_history_session_id'), 'session_history', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_session_history_session_id'), table_name='session_history')
    op.drop_table('session_history')
    op.drop_index(op.f('ix_coding_run_thread_id'), table_name='coding_run')
    op.drop_index(op.f('ix_coding_run_status'), table_name='coding_run')
    op.drop_index(op.f('ix_coding_run_repository_session_id'), table_name='coding_run')
    op.drop_table('coding_run')
    op.drop_index(op.f('ix_repository_session_repository_id'), table_name='repository_session')
    op.drop_index(op.f('ix_repository_session_user_id'), table_name='repository_session')
    op.drop_table('repository_session')
    op.drop_index(op.f('ix_repository_document_repository_id'), table_name='repository_document')
    op.drop_table('repository_document')
    op.drop_index(op.f('ix_repository_user_id'), table_name='repository')
    op.drop_index(op.f('ix_repository_status'), table_name='repository')
    op.drop_index(op.f('ix_repository_name'), table_name='repository')
    op.drop_table('repository')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
