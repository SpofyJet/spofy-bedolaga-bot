"""tariff_lifetime_pricing: флаги «вечного» тарифа

- switch_full_price: переход НА тариф по полной цене минимального периода,
  возврат на тарифы ниже tier_level — бесплатно
- device_price_flat: фиксированная (разовая) цена за доп. устройство

Revision ID: 0100
Revises: 0099
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0100'
down_revision: Union[str, None] = '0099'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c['name'] for c in inspector.get_columns('tariffs')}

    if 'switch_full_price' not in existing:
        op.add_column(
            'tariffs',
            sa.Column('switch_full_price', sa.Boolean(), nullable=False, server_default='false'),
        )
    if 'device_price_flat' not in existing:
        op.add_column(
            'tariffs',
            sa.Column('device_price_flat', sa.Boolean(), nullable=False, server_default='false'),
        )


def downgrade() -> None:
    op.drop_column('tariffs', 'device_price_flat')
    op.drop_column('tariffs', 'switch_full_price')
