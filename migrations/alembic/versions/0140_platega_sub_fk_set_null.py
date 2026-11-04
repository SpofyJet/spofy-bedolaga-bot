"""platega_subscriptions.subscription_id: ON DELETE CASCADE -> SET NULL.

With CASCADE, deleting a subscription silently removed its Platega recurring
binding, so the next charge webhook found nothing: the customer kept being
charged with no service and no trace. SET NULL keeps the record (user, amount,
SubscriptionId), and the charge callback can cancel the binding on Platega's side
and credit the money to the balance.

Idempotent: a database that already has SET NULL / nullable is left alone.
Downgrade deletes rows whose subscription is gone (exactly what CASCADE would
have removed) and restores CASCADE + NOT NULL.

Revision ID: 0140
Revises: 0139
"""

import sqlalchemy as sa
from alembic import op


revision = '0140'
down_revision = '0139'
branch_labels = None
depends_on = None

TABLE = 'platega_subscriptions'
COLUMN = 'subscription_id'
FK_NAME = 'platega_subscriptions_subscription_id_fkey'


def _subscription_fks(inspector) -> list[dict]:
    return [
        fk
        for fk in inspector.get_foreign_keys(TABLE)
        if fk.get('constrained_columns') == [COLUMN] and fk.get('referred_table') == 'subscriptions'
    ]


def _set_fk(ondelete: str, nullable: bool) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    fks = _subscription_fks(inspector)
    current = {str((fk.get('options') or {}).get('ondelete') or '').upper() for fk in fks}
    column = next(c for c in inspector.get_columns(TABLE) if c['name'] == COLUMN)
    if len(fks) == 1 and current == {ondelete} and bool(column['nullable']) == nullable:
        return
    with op.batch_alter_table(TABLE) as batch_op:
        for fk in fks:
            if fk.get('name'):
                batch_op.drop_constraint(fk['name'], type_='foreignkey')
        batch_op.alter_column(COLUMN, existing_type=sa.Integer(), nullable=nullable)
        batch_op.create_foreign_key(FK_NAME, 'subscriptions', [COLUMN], ['id'], ondelete=ondelete)


def upgrade() -> None:
    _set_fk('SET NULL', nullable=True)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        op.execute(sa.text(f'DELETE FROM {TABLE} WHERE {COLUMN} IS NULL'))
    _set_fk('CASCADE', nullable=False)
