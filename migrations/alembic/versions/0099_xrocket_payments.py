"""xrocket_payments: таблица платежей xRocket Pay

Revision ID: 0095
Revises: 0094
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.database.models import AwareDateTime


revision: str = '0099'
down_revision: Union[str, None] = '0098'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'xrocket_payments' in inspector.get_table_names():
        return

    op.create_table(
        'xrocket_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('invoice_id', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.String(length=50), nullable=False),
        sa.Column('asset', sa.String(length=20), nullable=False),
        sa.Column('amount_kopeks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fiat_rate', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('pay_url', sa.Text(), nullable=True),
        sa.Column('paid_at', AwareDateTime(), nullable=True),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('created_at', AwareDateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', AwareDateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_xrocket_payments_id'), 'xrocket_payments', ['id'])
    op.create_index(op.f('ix_xrocket_payments_invoice_id'), 'xrocket_payments', ['invoice_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_xrocket_payments_invoice_id'), table_name='xrocket_payments')
    op.drop_index(op.f('ix_xrocket_payments_id'), table_name='xrocket_payments')
    op.drop_table('xrocket_payments')
