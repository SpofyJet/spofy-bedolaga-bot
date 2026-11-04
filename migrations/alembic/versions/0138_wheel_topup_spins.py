"""Fortune wheel: free spins for top-ups, device/discount/extra-spin prizes.

Adds the top-up spin settings to wheel_configs and the won-device bonus to subscriptions.
If the wheel was never set up (no prizes), seeds a ready prize table and turns the
wheel on in top-up mode, so the feature works right after deploy; an admin-configured
wheel is left exactly as it is (top-up spins stay off until enabled in the admin).

Revision ID: 0138
Revises: 0137
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op


revision = '0138'
down_revision = '0137'
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {col['name'] for col in sa.inspect(op.get_bind()).get_columns(table)}


# (prize_type, prize_value, display_name, emoji, color, prize_value_kopeks, manual_probability)
DEFAULT_PRIZES = [
    ('subscription_days', 1, '+1 день', '📅', '#3B82F6', 700, 0.30),
    ('discount', 10, 'Скидка 10%', '🏷️', '#8B5CF6', 2000, 0.20),
    ('subscription_days', 3, '+3 дня', '🗓️', '#0EA5E9', 2000, 0.15),
    ('traffic_gb', 10, '+10 ГБ обходов', '🚀', '#14B8A6', 1500, 0.10),
    ('balance_bonus', 2500, '25 ₽ на баланс', '💰', '#F59E0B', 2500, 0.10),
    ('extra_spin', 1, 'Ещё спин', '🔄', '#EC4899', 1500, 0.09),
    ('device_slot', 1, '+1 устройство', '📱', '#22C55E', 5000, 0.05),
    ('discount', 25, 'Скидка 25%', '💎', '#EF4444', 5000, 0.01),
]


def upgrade() -> None:
    bind = op.get_bind()
    cfg_cols = _columns('wheel_configs')
    if 'topup_spins_enabled' not in cfg_cols:
        op.add_column(
            'wheel_configs',
            sa.Column('topup_spins_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if 'topup_spin_threshold_kopeks' not in cfg_cols:
        op.add_column(
            'wheel_configs',
            sa.Column('topup_spin_threshold_kopeks', sa.Integer(), nullable=False, server_default='15000'),
        )
    if 'topup_spin_value_kopeks' not in cfg_cols:
        op.add_column(
            'wheel_configs',
            sa.Column('topup_spin_value_kopeks', sa.Integer(), nullable=False, server_default='1500'),
        )
    if 'topup_spins_since' not in cfg_cols:
        op.add_column('wheel_configs', sa.Column('topup_spins_since', sa.DateTime(timezone=True), nullable=True))

    sub_cols = _columns('subscriptions')
    if 'wheel_bonus_devices' not in sub_cols:
        op.add_column(
            'subscriptions',
            sa.Column('wheel_bonus_devices', sa.Integer(), nullable=False, server_default='0'),
        )
    if 'wheel_bonus_devices_until' not in sub_cols:
        op.add_column(
            'subscriptions', sa.Column('wheel_bonus_devices_until', sa.DateTime(timezone=True), nullable=True)
        )

    # Колесо ещё не настраивали — готовый набор призов и режим «спины за пополнения».
    prizes_count = bind.execute(sa.text('SELECT count(*) FROM wheel_prizes')).scalar() or 0
    if prizes_count:
        return
    now = datetime.now(UTC)
    exists = bind.execute(sa.text('SELECT id FROM wheel_configs WHERE id = 1')).scalar()
    if exists is None:
        bind.execute(
            sa.text(
                'INSERT INTO wheel_configs (id, is_enabled, name, spin_cost_stars, spin_cost_days, '
                'spin_cost_stars_enabled, spin_cost_days_enabled, rtp_percent, daily_spin_limit, '
                'min_subscription_days_for_day_payment, promo_prefix, promo_validity_days, created_at, updated_at) '
                "VALUES (1, false, 'Колесо призов', 10, 1, false, false, 80, 5, 3, 'WHEEL', 7, :now, :now)"
            ),
            {'now': now},
        )
    bind.execute(
        sa.text(
            "UPDATE wheel_configs SET is_enabled = true, name = 'Колесо призов', topup_spins_enabled = true, "
            'spin_cost_stars_enabled = false, spin_cost_days_enabled = false, topup_spins_since = :now, '
            'updated_at = :now WHERE id = 1'
        ),
        {'now': now},
    )
    for order, (ptype, value, name, emoji, color, kopeks, prob) in enumerate(DEFAULT_PRIZES):
        bind.execute(
            sa.text(
                'INSERT INTO wheel_prizes (config_id, prize_type, prize_value, display_name, emoji, color, '
                'prize_value_kopeks, sort_order, manual_probability, is_active, promo_balance_bonus_kopeks, '
                'promo_subscription_days, promo_traffic_gb, created_at, updated_at) '
                'VALUES (1, :ptype, :value, :name, :emoji, :color, :kopeks, :order, :prob, true, 0, 0, 0, :now, :now)'
            ),
            {
                'ptype': ptype,
                'value': value,
                'name': name,
                'emoji': emoji,
                'color': color,
                'kopeks': kopeks,
                'order': order,
                'prob': prob,
                'now': now,
            },
        )


def downgrade() -> None:
    for column in (
        'topup_spins_since',
        'topup_spin_value_kopeks',
        'topup_spin_threshold_kopeks',
        'topup_spins_enabled',
    ):
        op.drop_column('wheel_configs', column)
    op.drop_column('subscriptions', 'wheel_bonus_devices_until')
    op.drop_column('subscriptions', 'wheel_bonus_devices')
