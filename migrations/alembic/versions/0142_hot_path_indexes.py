"""Indexes for promo activation and recent payment lookups.

promocode_uses had no index that starts with promocode_id, so counting and
loading the uses of a popular code read the whole table. Recent payment queries
filter by created_at. The tables are small enough for a plain CREATE INDEX to
finish in well under a second at startup.

Idempotent: an index that already exists is left alone.

Revision ID: 0142
Revises: 0141
"""

from alembic import op


revision = '0142'
down_revision = '0141'
branch_labels = None
depends_on = None

INDEXES = {
    'ix_promocode_uses_promocode_id': ('promocode_uses', 'promocode_id'),
    'ix_platega_payments_created_at': ('platega_payments', 'created_at'),
    'ix_wata_payments_created_at': ('wata_payments', 'created_at'),
    'ix_transactions_created_at': ('transactions', 'created_at'),
}


def upgrade() -> None:
    for name, (table, columns) in INDEXES.items():
        op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})')


def downgrade() -> None:
    for name in INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')
