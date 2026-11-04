"""Fortune wheel: 1 free spin per 1000 ₽ of top-ups; Spofy palette for the seeded prizes.

Only touches values 0138 put there: a threshold changed in the admin, or a prize an admin
recoloured or renamed, stays as it is.

Revision ID: 0139
Revises: 0138
"""

import sqlalchemy as sa
from alembic import op


revision = '0139'
down_revision = '0138'
branch_labels = None
depends_on = None

# (display_name, color seeded by 0138, new color)
PALETTE = [
    ('+1 день', '#3B82F6', '#2563EB'),
    ('Скидка 10%', '#8B5CF6', '#4F46E5'),
    ('+3 дня', '#0EA5E9', '#0284C7'),
    ('25 ₽ на баланс', '#F59E0B', '#0F766E'),
    ('Ещё спин', '#EC4899', '#7C3AED'),
    ('+1 устройство', '#22C55E', '#059669'),
    ('Скидка 25%', '#EF4444', '#D97706'),
]


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            'UPDATE wheel_configs SET topup_spin_threshold_kopeks = 100000, topup_spin_value_kopeks = 10000 '
            'WHERE topup_spin_threshold_kopeks = 15000 AND topup_spin_value_kopeks = 1500'
        )
    )
    for name, old, new in PALETTE:
        bind.execute(
            sa.text('UPDATE wheel_prizes SET color = :new WHERE display_name = :name AND upper(color) = :old'),
            {'name': name, 'old': old.upper(), 'new': new},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            'UPDATE wheel_configs SET topup_spin_threshold_kopeks = 15000, topup_spin_value_kopeks = 1500 '
            'WHERE topup_spin_threshold_kopeks = 100000 AND topup_spin_value_kopeks = 10000'
        )
    )
    for name, old, new in PALETTE:
        bind.execute(
            sa.text('UPDATE wheel_prizes SET color = :old WHERE display_name = :name AND upper(color) = :new'),
            {'name': name, 'old': old, 'new': new.upper()},
        )
