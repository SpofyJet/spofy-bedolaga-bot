"""remove NaloGO receipt columns

Revision ID: 0144
Revises: 0143
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0144'
down_revision: str | None = '0143'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ('transactions', 'guest_purchases')


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'DROP INDEX IF EXISTS ix_{table}_receipt_uuid')
        op.execute(f'ALTER TABLE {table} DROP COLUMN IF EXISTS receipt_uuid')
        op.execute(f'ALTER TABLE {table} DROP COLUMN IF EXISTS receipt_created_at')


def downgrade() -> None:
    columns = {
        'receipt_uuid': sa.String(length=255),
        'receipt_created_at': sa.DateTime(timezone=True),
    }
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        existing = {column['name'] for column in inspector.get_columns(table)}
        for name, column_type in columns.items():
            if name not in existing:
                op.add_column(table, sa.Column(name, column_type, nullable=True))
        op.execute(f'CREATE INDEX IF NOT EXISTS ix_{table}_receipt_uuid ON {table} (receipt_uuid)')
