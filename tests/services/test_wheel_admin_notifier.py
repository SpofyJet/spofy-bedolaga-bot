"""Админ узнаёт о каждом спине колеса; выданные админом спины считаются, но не спины."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.crud.wheel import grant_free_spins
from app.database.models import WheelPrizeType, WheelSpinPaymentType
from app.services.wheel_admin_notifier import build_spin_admin_message


def _msg(**kw) -> str:
    base = dict(
        user_display='Алексей',
        user_id_label='Telegram ID',
        user_id_display='<code>42</code>',
        username_link='@alexey',
        payment_type=WheelSpinPaymentType.TOPUP_CREDIT.value,
        payment_amount=1,
        free_left=1,
        prize_emoji='💎',
        prize_name='+30 дней',
        promocode=None,
        when='04.11.2026 13:00:00',
    )
    base.update(kw)
    return build_spin_admin_message(**base)


def test_free_spin_shows_prize_and_spins_left() -> None:
    text = _msg()
    assert 'СПИН КОЛЕСА ПРИЗОВ' in text
    assert 'бесплатный спин (осталось: 1)' in text
    assert '💎 <b>+30 дней</b>' in text
    assert 'Промокод' not in text


def test_stars_spin_and_promocode_are_escaped() -> None:
    text = _msg(
        payment_type=WheelSpinPaymentType.TELEGRAM_STARS.value,
        payment_amount=50,
        free_left=None,
        prize_name='Скидка <15%>',
        promocode='AB<C>',
    )
    assert '⭐ 50 Stars' in text
    assert 'Скидка &lt;15%&gt;' in text
    assert '<code>AB&lt;C&gt;</code>' in text


@pytest.mark.asyncio
async def test_grant_free_spins_is_an_extra_spin_row_outside_spin_stats() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    row = await grant_free_spins(db, user_id=7, count=2)
    db.add.assert_called_once_with(row)
    assert row.payment_type == WheelSpinPaymentType.ADMIN_GRANT.value
    assert row.prize_type == WheelPrizeType.EXTRA_SPIN.value
    assert row.prize_value == 2
    assert row.payment_value_kopeks == 0 and row.prize_value_kopeks == 0
    assert row.is_applied is True


@pytest.mark.asyncio
async def test_grant_rejects_non_positive_count() -> None:
    with pytest.raises(ValueError):
        await grant_free_spins(MagicMock(), user_id=7, count=0)
