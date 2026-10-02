"""subscription_bypass_suspended: обходы отключены из-за исчерпанного трафика

- subscriptions.bypass_suspended_at: когда подписку перевели в сквад Bypass-Off
  (NULL — обходы работают). См. app/services/bypass_downgrade.py.

Revision ID: 0134
Revises: 0133
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0134'
down_revision: Union[str, None] = '0133'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('subscriptions')}
    if 'bypass_suspended_at' not in existing:
        op.add_column('subscriptions', sa.Column('bypass_suspended_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('subscriptions')}
    if 'bypass_suspended_at' in existing:
        op.drop_column('subscriptions', 'bypass_suspended_at')
