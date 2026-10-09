"""«Скопировать» одним нажатием, конфетти на оплате, подписка за Stars раз в 30 дней."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

from app.config import settings
from app.keyboards import inline
from app.middlewares import success_effect_request as effect_module
from app.middlewares.success_effect_request import SuccessEffectRequestMiddleware, is_success_message


LINK = 'https://sub.spofyltd.ru/AbCdEf123'


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)
    monkeypatch.setattr(effect_module, '_effect_unavailable', False)


# ---------------- «скопировать» ----------------


def _subscription():
    tariff = SimpleNamespace(
        id=2, is_daily=False, is_free=False, name='T', traffic_limit_gb=0, device_limit=3,
        can_topup_traffic=lambda: False, device_price_kopeks=5000,
    )  # fmt: skip
    return SimpleNamespace(
        id=1, tariff_id=2, tariff=tariff, is_trial=False, traffic_limit_gb=0, actual_status='active',
        is_active=True, subscription_url=LINK, subscription_crypto_link=None, remnawave_short_uuid=None,
        is_daily_paused=False, connected_squads=[],
    )  # fmt: skip


def test_subscription_screen_copies_the_link_in_one_tap(monkeypatch):
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs', raising=False)
    monkeypatch.setattr(inline, 'get_display_subscription_link', lambda sub: LINK)
    kb = inline.get_subscription_keyboard('ru', True, False, _subscription())
    first = kb.inline_keyboard[0]
    assert [b.text for b in first] == ['🔗 Подключиться', '📋 Ссылка']
    assert first[1].copy_text.text == LINK
    assert all(len(b.text) <= 15 for b in first)  # парные подписи читаются на телефоне


def test_no_link_means_no_copy_button(monkeypatch):
    monkeypatch.setattr(inline, 'get_display_subscription_link', lambda sub: None)
    kb = inline.get_subscription_keyboard('ru', True, False, _subscription())
    assert not any(b.copy_text for row in kb.inline_keyboard for b in row)


def test_referral_screen_offers_to_copy_the_link():
    kb = inline.get_referral_keyboard(
        'ru', share_url='https://t.me/share', copy_link='https://t.me/spofyvpnbot?start=ref1'
    )
    copy_rows = [row for row in kb.inline_keyboard if row[0].copy_text]
    assert copy_rows and copy_rows[0][0].copy_text.text.endswith('start=ref1')
    assert len(copy_rows[0]) == 1  # одна кнопка в строке, как остальные на этом экране


# ---------------- конфетти на оплате ----------------


@pytest.mark.parametrize(
    'text',
    [
        '✅ <b>Пополнение успешно!</b>\n\nСумма: 100',
        '🎉 <b>Баланс пополнен!</b>\n\n⭐ Списано звёзд: 5',
        '✅ <b>Оплата получена!</b>\n\n💰 Сумма: 1',
        '🎉 <b>Подписка успешно оформлена!</b>\n\nТариф',
    ],
)
def test_success_messages_are_recognized(text):
    assert is_success_message(text) is True


@pytest.mark.parametrize(
    'text', ['❌ <b>Недостаточно средств</b>', 'Привет!', '⏳ <b>Подписка закончится</b>', None, '']
)
def test_other_messages_are_not(text):
    assert is_success_message(text) is False


async def _send(method):
    make_request = AsyncMock(return_value='sent')
    await SuccessEffectRequestMiddleware()(make_request, MagicMock(), method)
    return make_request


async def test_private_success_message_gets_the_effect():
    method = SendMessage(chat_id=555, text='✅ <b>Пополнение успешно!</b>')
    await _send(method)
    assert method.message_effect_id == settings.PAYMENT_SUCCESS_EFFECT_ID


async def test_groups_other_texts_and_disabled_setting_get_no_effect(monkeypatch):
    group = SendMessage(chat_id=-100123, text='✅ <b>Пополнение успешно!</b>')
    plain = SendMessage(chat_id=555, text='Привет')
    await _send(group)
    await _send(plain)
    assert group.message_effect_id is None and plain.message_effect_id is None
    monkeypatch.setattr(settings, 'PAYMENT_SUCCESS_EFFECT_ID', '', raising=False)
    off = SendMessage(chat_id=555, text='✅ <b>Пополнение успешно!</b>')
    await _send(off)
    assert off.message_effect_id is None


async def test_rejected_effect_falls_back_to_a_plain_message():
    method = SendMessage(chat_id=555, text='✅ <b>Пополнение успешно!</b>')
    calls = []

    async def make_request(bot, m):
        calls.append(m.message_effect_id)
        if m.message_effect_id:
            raise TelegramBadRequest(method=m, message='Bad Request: message effect is not available')
        return 'sent'

    result = await SuccessEffectRequestMiddleware()(make_request, MagicMock(), method)
    assert result == 'sent' and calls == [settings.PAYMENT_SUCCESS_EFFECT_ID, None]
    assert effect_module._effect_unavailable is True  # больше не пробуем до перезапуска


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
