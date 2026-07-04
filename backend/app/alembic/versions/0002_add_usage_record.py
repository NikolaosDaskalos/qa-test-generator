"""Add the usage_record table for AI Cost.

Revision ID: 0002_add_usage_record
Revises: 0001_initial_schema
Create Date: 2026-07-03 09:00:00.000000
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "0002_add_usage_record"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('usage_record',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('model', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('node_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('total_tokens', sa.Integer(), nullable=False),
    sa.Column('cost', sa.Float(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('repository_id', sa.Uuid(), nullable=False),
    sa.Column('repository_session_id', sa.Uuid(), nullable=False),
    sa.Column('session_history_id', sa.Uuid(), nullable=True),
    sa.Column('coding_run_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['repository_id'], ['repository.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['repository_session_id'], ['repository_session.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_history_id'], ['session_history.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['coding_run_id'], ['coding_run.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_record_user_id'), 'usage_record', ['user_id'], unique=False)
    op.create_index(op.f('ix_usage_record_repository_id'), 'usage_record', ['repository_id'], unique=False)
    op.create_index(op.f('ix_usage_record_repository_session_id'), 'usage_record', ['repository_session_id'], unique=False)
    op.create_index(op.f('ix_usage_record_session_history_id'), 'usage_record', ['session_history_id'], unique=False)
    op.create_index(op.f('ix_usage_record_coding_run_id'), 'usage_record', ['coding_run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_record_coding_run_id'), table_name='usage_record')
    op.drop_index(op.f('ix_usage_record_session_history_id'), table_name='usage_record')
    op.drop_index(op.f('ix_usage_record_repository_session_id'), table_name='usage_record')
    op.drop_index(op.f('ix_usage_record_repository_id'), table_name='usage_record')
    op.drop_index(op.f('ix_usage_record_user_id'), table_name='usage_record')
    op.drop_table('usage_record')
