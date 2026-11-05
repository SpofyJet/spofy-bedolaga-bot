"""Indexes on foreign keys of the busiest tables.

PostgreSQL does not index a foreign key by itself. Every user, subscription or
transaction delete made it scan these tables in full: subscription_events alone
had read about 20 billion rows. The tables are small enough for a plain CREATE
INDEX to finish in well under a second at startup.

Idempotent: an index that already exists is left alone.

Revision ID: 0141
Revises: 0140
"""

from alembic import op


revision = '0141'
down_revision = '0140'
branch_labels = None
depends_on = None

INDEXES = {
    'ix_subscription_events_user_id': ('subscription_events', 'user_id'),
    'ix_subscription_events_subscription_id': ('subscription_events', 'subscription_id'),
    'ix_subscription_events_transaction_id': ('subscription_events', 'transaction_id'),
    'ix_sent_notifications_user_id': ('sent_notifications', 'user_id'),
    'ix_sent_notifications_subscription_type_days': (
        'sent_notifications',
        'subscription_id, notification_type, days_before',
    ),
    'ix_platega_payments_user_id': ('platega_payments', 'user_id'),
    'ix_platega_payments_transaction_id': ('platega_payments', 'transaction_id'),
    'ix_cryptobot_payments_user_id': ('cryptobot_payments', 'user_id'),
    'ix_cryptobot_payments_transaction_id': ('cryptobot_payments', 'transaction_id'),
    'ix_wata_payments_user_id': ('wata_payments', 'user_id'),
    'ix_wata_payments_transaction_id': ('wata_payments', 'transaction_id'),
    'ix_referral_earnings_user_id': ('referral_earnings', 'user_id'),
    'ix_referral_earnings_referral_id': ('referral_earnings', 'referral_id'),
    'ix_referral_earnings_referral_transaction_id': ('referral_earnings', 'referral_transaction_id'),
    'ix_subscription_conversions_user_id': ('subscription_conversions', 'user_id'),
    'ix_discount_offers_subscription_id': ('discount_offers', 'subscription_id'),
}


def upgrade() -> None:
    for name, (table, columns) in INDEXES.items():
        op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})')


def downgrade() -> None:
    for name in INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')
