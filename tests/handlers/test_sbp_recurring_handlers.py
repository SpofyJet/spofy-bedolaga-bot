"""Автоплатёж в боте после удаления СБП-автопродления Platega.

Кнопки СБП-автопродления живут в старых сообщениях и рассылках — нажатие на них
должно получать ответ «недоступно», а не крутящийся индикатор. Экраны автоплатежа
и подтверждения покупки больше не предлагают СБП-привязку.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import app.handlers.subscription.autopay as autopay_mod


def _make_callback():
    cb = MagicMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_user():
    user = MagicMock()
    user.id = 1
    user.language = 'ru'
    return user


def _keyboard_callbacks(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


async def test_autopay_menu_daily_tariff_has_no_sbp_entry(monkeypatch):
    cb, user, db = _make_callback(), _make_user(), AsyncMock()
    subscription = SimpleNamespace(id=10, tariff=SimpleNamespace(is_daily=True))

    monkeypatch.setattr(autopay_mod, '_resolve_subscription', AsyncMock(return_value=(subscription, 10)))

    await autopay_mod.handle_autopay_menu(cb, user, db)

    cb.message.edit_text.assert_awaited_once()
    _, kwargs = cb.message.edit_text.call_args
    assert _keyboard_callbacks(kwargs['reply_markup']) == ['menu_subscription']


async def test_toggle_autopay_enable_blocked_for_trial(monkeypatch):
    cb, user, db = _make_callback(), _make_user(), AsyncMock()
    cb.data = 'autopay_enable'
    subscription = SimpleNamespace(id=10, tariff_id=5, tariff=None, is_trial=True, autopay_enabled=False)

    monkeypatch.setattr(autopay_mod, '_resolve_subscription', AsyncMock(return_value=(subscription, 10)))
    mock_update = AsyncMock(return_value=subscription)
    monkeypatch.setattr(autopay_mod, 'update_subscription_autopay', mock_update)

    await autopay_mod.toggle_autopay(cb, user, db)

    mock_update.assert_not_awaited()


async def test_stale_sbp_button_answers_unavailable():
    cb, user = _make_callback(), _make_user()
    cb.data = 'sbp_recurring_enable'

    await autopay_mod.handle_sbp_recurring_unavailable(cb, user)

    cb.answer.assert_awaited_once()
    assert cb.answer.await_args.kwargs.get('show_alert') is True
    cb.message.edit_text.assert_not_awaited()


def test_tariff_confirm_keyboards_have_no_sbp_button():
    from app.handlers.subscription.tariff_purchase import (
        get_daily_tariff_confirm_keyboard,
        get_tariff_confirm_keyboard,
    )

    assert _keyboard_callbacks(get_tariff_confirm_keyboard(5, 30, 'ru')) == ['tariff_confirm:5:30', 'tariff_select:5']
    assert _keyboard_callbacks(get_daily_tariff_confirm_keyboard(7, 'ru')) == ['daily_tariff_confirm:7', 'menu_buy']
