"""Экраны устройств, рефералов и оплаты идут без баннера; главная и подписка — с ним."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.middlewares.banner_variant import is_text_only_screen
from app.utils import message_patch


@pytest.mark.parametrize(
    'callback',
    [
        'subscription_manage_devices', 'subscription_change_devices', 'devices_page_2', 'reset_device_0_1',
        'device_rename_1_1', 'menu_referrals', 'referral_list', 'referral_create_invite', 'menu_balance',
        'balance_topup', 'topup_platega_m2', 'topup_amount|wata|27000', 'check_platega_123',
    ],
)  # fmt: skip
def test_device_referral_and_payment_screens_have_no_banner(callback):
    assert is_text_only_screen(callback, None) is True


@pytest.mark.parametrize(
    'callback', ['back_to_menu', 'menu_subscription', 'menu_support', 'menu_info', 'menu_trial', 'menu_buy', 'tariff_select:2', None]
)  # fmt: skip
def test_main_subscription_and_other_screens_keep_the_banner(callback):
    assert is_text_only_screen(callback, None) is False


def test_amount_and_withdrawal_input_states_have_no_banner():
    assert is_text_only_screen(None, 'BalanceStates:waiting_for_amount') is True
    assert is_text_only_screen(None, 'ReferralWithdrawalStates:waiting_for_amount') is True
    assert is_text_only_screen(None, 'TicketStates:waiting_for_title') is False


@pytest.mark.parametrize('callback', ['back_to_menu', 'menu_subscription', 'menu_info'])
def test_navigation_from_amount_input_state_keeps_the_banner(callback):
    # Регрессия: навигация кнопкой из «ожидания суммы» не должна ронять баннер
    # целевого экрана — иначе фото-меню удалялось и главное меню оставалось текстовым.
    assert is_text_only_screen(callback, 'BalanceStates:waiting_for_amount') is False
    assert is_text_only_screen(callback, 'ReferralWithdrawalStates:waiting_for_amount') is False


async def test_answer_without_banner_sends_plain_text(monkeypatch):
    monkeypatch.setattr(settings, 'ENABLE_LOGO_MODE', True, raising=False)
    original = AsyncMock(return_value='sent')
    monkeypatch.setattr(message_patch, '_original_answer', original)
    token = message_patch.set_banner_text_only(True)
    try:
        assert await message_patch._answer_with_photo(MagicMock(), 'текст', reply_markup=None) == 'sent'
    finally:
        message_patch.reset_banner_text_only(token)
    original.assert_awaited_once()


async def test_editing_a_banner_message_into_a_text_screen_replaces_it(monkeypatch):
    monkeypatch.setattr(settings, 'ENABLE_LOGO_MODE', True, raising=False)
    original_answer = AsyncMock(return_value='new text message')
    monkeypatch.setattr(message_patch, '_original_answer', original_answer)
    message = SimpleNamespace(text=None, photo=[SimpleNamespace(file_id='x')], delete=AsyncMock())
    token = message_patch.set_banner_text_only(True)
    try:
        result = await message_patch._edit_with_photo(message, 'экран устройств')
    finally:
        message_patch.reset_banner_text_only(token)
    assert result == 'new text message'
    message.delete.assert_awaited_once()  # фото-сообщение с баннером заменено текстовым


async def test_middleware_sets_the_flag_only_for_the_handler(monkeypatch):
    from aiogram.types import CallbackQuery

    from app.middlewares.banner_variant import BannerVariantMiddleware

    seen = {}

    async def handler(event, data):
        seen['text_only'] = message_patch.banner_text_only()
        return 'ok'

    event = MagicMock(spec=CallbackQuery)
    event.data = 'menu_referrals'
    state = MagicMock(get_state=AsyncMock(return_value=None))
    data = {'db_user': SimpleNamespace(subscriptions=[], language='ru'), 'state': state}
    assert await BannerVariantMiddleware()(handler, event, data) == 'ok'
    assert seen['text_only'] is True
    assert message_patch.banner_text_only() is False  # после обработчика флаг сброшен
    event.data = 'menu_subscription'
    await BannerVariantMiddleware()(handler, event, data)
    assert seen['text_only'] is False
