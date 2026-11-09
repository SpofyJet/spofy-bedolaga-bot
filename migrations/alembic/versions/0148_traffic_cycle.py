"""Add monthly traffic cycle columns.

Live subscriptions are marked as reset now, so the first reset happens on the
next purchase day rather than for everyone at once.

Idempotent.

Revision ID: 0148
Revises: 0147
"""

from alembic import op


revision = '0148'
down_revision = '0147'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS traffic_cycle_anchor_at timestamptz')
    op.execute('ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS traffic_cycle_reset_at timestamptz')
    op.execute(
        'UPDATE subscriptions SET traffic_cycle_reset_at = now() '
        "WHERE traffic_cycle_reset_at IS NULL AND status IN ('active', 'limited') AND traffic_limit_gb > 0"
    )


def downgrade() -> None:
    op.execute('ALTER TABLE subscriptions DROP COLUMN IF EXISTS traffic_cycle_reset_at')
    op.execute('ALTER TABLE subscriptions DROP COLUMN IF EXISTS traffic_cycle_anchor_at')
