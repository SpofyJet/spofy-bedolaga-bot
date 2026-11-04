"""Fortune wheel: 1 free spin per 1000 ₽ of top-ups; bigger prizes to match; Spofy palette.

Only touches values 0138 put there: a threshold changed in the admin, or a prize an admin
recoloured, renamed, revalued or reweighted, stays as it is.

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

# A spin now takes 1000 ₽ of top-ups instead of 150 ₽, so every seeded prize goes up a step.
# Each row: (as seeded by 0138, after 0139) = (display_name, prize_type, prize_value,
# prize_value_kopeks, manual_probability). Probabilities still sum to 1.
PRIZES = [
    (('+1 день', 'subscription_days', 1, 700, 0.35), ('+3 дня', 'subscription_days', 3, 2100, 0.35)),
    (('Скидка 10%', 'discount', 10, 2000, 0.20), ('Скидка 15%', 'discount', 15, 3000, 0.20)),
    (('+3 дня', 'subscription_days', 3, 2000, 0.20), ('+7 дней', 'subscription_days', 7, 4900, 0.18)),
    (('25 ₽ на баланс', 'balance_bonus', 2500, 2500, 0.10), ('100 ₽ на баланс', 'balance_bonus', 10000, 10000, 0.10)),
    (('Ещё спин', 'extra_spin', 1, 1500, 0.09), ('Ещё спин', 'extra_spin', 1, 5000, 0.10)),
    (('+1 устройство', 'device_slot', 1, 5000, 0.05), ('+1 устройство', 'device_slot', 1, 5000, 0.05)),
    # Jackpot: a month of subscription instead of a 25% discount.
    (('Скидка 25%', 'discount', 25, 5000, 0.01), ('+30 дней', 'subscription_days', 30, 21000, 0.02)),
]

_MATCH = (
    'display_name = :name AND prize_type = :ptype AND prize_value = :value '
    'AND prize_value_kopeks = :kopeks AND abs(coalesce(manual_probability, -1) - :prob) < 0.0001'
)
_SET = (
    'display_name = :name, prize_type = :ptype, prize_value = :value, '
    'prize_value_kopeks = :kopeks, manual_probability = :prob'
)


def _fields(row: tuple) -> dict:
    name, ptype, value, kopeks, prob = row
    return {'name': name, 'ptype': ptype, 'value': value, 'kopeks': kopeks, 'prob': prob}


def _move_prizes(bind, pairs: list[tuple[tuple, tuple]]) -> None:
    # Through a temporary name first: the old «+3 дня» becomes «+7 дней» while the old
    # «+1 день» becomes «+3 дня», and a one-pass update would match the wrong row.
    for index, (src, _dst) in enumerate(pairs):
        bind.execute(
            sa.text(f'UPDATE wheel_prizes SET display_name = :tmp WHERE {_MATCH}'),
            {'tmp': f'__wheel0139_{index}', **_fields(src)},
        )
    for index, (_src, dst) in enumerate(pairs):
        bind.execute(
            sa.text(f'UPDATE wheel_prizes SET {_SET} WHERE display_name = :tmp'),
            {'tmp': f'__wheel0139_{index}', **_fields(dst)},
        )


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            'UPDATE wheel_configs SET topup_spin_threshold_kopeks = 100000, topup_spin_value_kopeks = 10000 '
            'WHERE topup_spin_threshold_kopeks = 15000 AND topup_spin_value_kopeks = 1500'
        )
    )
    # Colours are matched by the 0138 names, so they go before the prizes are renamed.
    for name, old, new in PALETTE:
        bind.execute(
            sa.text('UPDATE wheel_prizes SET color = :new WHERE display_name = :name AND upper(color) = :old'),
            {'name': name, 'old': old.upper(), 'new': new},
        )
    _move_prizes(bind, PRIZES)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            'UPDATE wheel_configs SET topup_spin_threshold_kopeks = 15000, topup_spin_value_kopeks = 1500 '
            'WHERE topup_spin_threshold_kopeks = 100000 AND topup_spin_value_kopeks = 10000'
        )
    )
    _move_prizes(bind, [(new, old) for old, new in PRIZES])
    for name, old, new in PALETTE:
        bind.execute(
            sa.text('UPDATE wheel_prizes SET color = :old WHERE display_name = :name AND upper(color) = :new'),
            {'name': name, 'old': old, 'new': new.upper()},
        )
