"""Replace Heleket with 2328.io.

Revision ID: 0145
Revises: 0144
"""

from collections.abc import Sequence

from alembic import op


revision: str = '0145'
down_revision: str | None = '0144'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = ('id', 'metadata_purchase_token', 'order_id', 'uuid')
COPIED_SETTINGS = ('MARKUP_PERCENT', 'RETURN_URL', 'SUCCESS_URL')


def _rename(old: str, new: str) -> None:
    op.execute(f'ALTER TABLE {old}_payments RENAME TO {new}_payments')
    op.execute(f'ALTER SEQUENCE IF EXISTS {old}_payments_id_seq RENAME TO {new}_payments_id_seq')
    op.execute(f'ALTER INDEX IF EXISTS {old}_payments_pkey RENAME TO {new}_payments_pkey')
    for suffix in INDEXES:
        op.execute(f'ALTER INDEX IF EXISTS ix_{old}_payments_{suffix} RENAME TO ix_{new}_payments_{suffix}')
    for suffix in ('transaction_id_fkey', 'user_id_fkey'):
        op.execute(
            f'DO $$ BEGIN '
            f"IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{old}_payments_{suffix}') THEN "
            f'ALTER TABLE {new}_payments RENAME CONSTRAINT {old}_payments_{suffix} TO {new}_payments_{suffix}; '
            f'END IF; END $$'
        )


def upgrade() -> None:
    _rename('heleket', 'pay2328')
    op.execute("UPDATE payment_method_configs SET method_id = 'pay2328' WHERE method_id = 'heleket'")
    for name in COPIED_SETTINGS:
        op.execute(
            f'INSERT INTO system_settings (key, value) '
            f"SELECT 'PAY2328_{name}', value FROM system_settings WHERE key = 'HELEKET_{name}' "
            f'ON CONFLICT (key) DO NOTHING'
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key IN ('PAY2328_MARKUP_PERCENT', 'PAY2328_RETURN_URL', 'PAY2328_SUCCESS_URL')"
    )
    op.execute("UPDATE payment_method_configs SET method_id = 'heleket' WHERE method_id = 'pay2328'")
    _rename('pay2328', 'heleket')
