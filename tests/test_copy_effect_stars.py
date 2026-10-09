"""«Скопировать» реферальную ссылку одним нажатием, подписка за Stars раз в 30 дней."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.keyboards import inline


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)


# ---------------- «скопировать» ----------------


def test_referral_screen_offers_to_copy_the_link():
    kb = inline.get_referral_keyboard(
        'ru', share_url='https://t.me/share', copy_link='https://t.me/spofyvpnbot?start=ref1'
    )
    copy_rows = [row for row in kb.inline_keyboard if row[0].copy_text]
    assert copy_rows and copy_rows[0][0].copy_text.text.endswith('start=ref1')
    assert len(copy_rows[0]) == 1  # одна кнопка в строке, как остальные на этом экране


# ---------------- Stars: подписка ----------------


async def test_stars_invoice_with_a_period_asks_telegram_for_a_recurring_charge():
    from app.services.payment.stars import TelegramStarsMixin

    service = TelegramStarsMixin()
    service.bot = MagicMock(create_invoice_link=AsyncMock(return_value='https://t.me/$abc'))
    service.stars_service = object()
    await service.create_stars_invoice(15900, 'Пополнение', payload='balance_1_15900', subscription_period=2592000)
    assert service.bot.create_invoice_link.await_args.kwargs['subscription_period'] == 2592000
    await service.create_stars_invoice(15900, 'Пополнение', payload='balance_1_15900')
    assert 'subscription_period' not in service.bot.create_invoice_link.await_args.kwargs  # обычный платёж как раньше


def test_stars_subscription_is_off_by_default():
    assert settings.TELEGRAM_STARS_SUBSCRIPTION_ENABLED is False


def test_subscription_screen_has_no_copy_link_button():
    from types import SimpleNamespace

    sub = SimpleNamespace(
        id=1, tariff_id=2, tariff=SimpleNamespace(
            id=2, is_daily=False, is_free=False, name='T', traffic_limit_gb=0, device_limit=3,
            can_topup_traffic=lambda: False, device_price_kopeks=5000,
        ), is_trial=False, traffic_limit_gb=0, actual_status='active', is_active=True,
        subscription_url='https://sub.spofyltd.ru/x', subscription_crypto_link=None, remnawave_short_uuid=None,
        is_daily_paused=False, connected_squads=[],
    )  # fmt: skip
    kb = inline.get_subscription_keyboard('ru', True, False, sub)
    assert not any(button.copy_text for row in kb.inline_keyboard for button in row)
