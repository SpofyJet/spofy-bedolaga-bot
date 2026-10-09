"""mass_send_jobs, decision_log и поля возобновления рассылок

- mass_send_jobs: массовые отправки (промопредложения), переживающие перезапуск бота;
- decision_log: журнал решений (антиабуз, награды, рассылки);
- broadcast_history.recipient_ids / resume_cursor / resume_config: возобновление обычных рассылок.

Revision ID: 0135
Revises: 0134
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0135'
down_revision: Union[str, None] = '0134'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'mass_send_jobs' not in tables:
        op.create_table(
            'mass_send_jobs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('kind', sa.String(40), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
            sa.Column('params', sa.JSON(), nullable=False),
            sa.Column('recipient_ids', sa.JSON(), nullable=False),
            sa.Column('cursor', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('sent', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('already', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_mass_send_jobs_id', 'mass_send_jobs', ['id'])
        op.create_index('ix_mass_send_jobs_status', 'mass_send_jobs', ['status'])

    if 'decision_log' not in tables:
        op.create_table(
            'decision_log',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('kind', sa.String(60), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('panel_user_id', sa.Integer(), nullable=True),
            sa.Column('summary', sa.Text(), nullable=False, server_default=''),
            sa.Column('details', sa.JSON(), nullable=True),
        )
        op.create_index('ix_decision_log_id', 'decision_log', ['id'])
        op.create_index('ix_decision_log_kind_created', 'decision_log', ['kind', 'created_at'])
        op.create_index('ix_decision_log_user', 'decision_log', ['user_id'])

    if 'broadcast_history' in tables:
        existing = {c['name'] for c in inspector.get_columns('broadcast_history')}
        if 'recipient_ids' not in existing:
            op.add_column('broadcast_history', sa.Column('recipient_ids', sa.JSON(), nullable=True))
        if 'resume_cursor' not in existing:
            op.add_column(
                'broadcast_history', sa.Column('resume_cursor', sa.Integer(), nullable=False, server_default='0')
            )
        if 'resume_config' not in existing:
            op.add_column('broadcast_history', sa.Column('resume_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'broadcast_history' in tables:
        existing = {c['name'] for c in inspector.get_columns('broadcast_history')}
        for name in ('resume_config', 'resume_cursor', 'recipient_ids'):
            if name in existing:
                op.drop_column('broadcast_history', name)
    for table in ('decision_log', 'mass_send_jobs'):
        if table in tables:
            op.drop_table(table)
