"""Главное меню без лишнего: баланс только тем, у кого он нужен; промокод и поддержка под рукой."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.keyboards.inline import get_main_menu_keyboard


@pytest.fixture(autouse=True)
def _bot_menu(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)
    monkeypatch.setattr(settings, 'SUPPORT_MENU_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'TRIAL_DURATION_DAYS', 2, raising=False)
    monkeypatch.setattr(settings, 'TRIAL_DISABLED_FOR', 'none', raising=False)


def _callbacks(markup):
    return [[b.callback_data or ('url' if b.url else 'webapp') for b in row] for row in markup.inline_keyboard]


def _flat(markup):
    return [c for row in _callbacks(markup) for c in row]


def test_new_user_has_no_empty_balance_but_has_promocode_and_support():
    kb = get_main_menu_keyboard(has_had_paid_subscription=False, has_active_subscription=False, balance_kopeks=0)
    flat = _flat(kb)
    assert 'menu_balance' not in flat
    assert flat[:2] == ['menu_trial', 'menu_buy']
    assert ['menu_promocode', 'menu_support'] in _callbacks(kb)


def test_balance_stays_for_people_with_money_or_paid_history():
    with_money = get_main_menu_keyboard(
        has_had_paid_subscription=False, has_active_subscription=False, balance_kopeks=5000
    )
    paid_before = get_main_menu_keyboard(
        has_had_paid_subscription=True, has_active_subscription=False, balance_kopeks=0
    )
    assert 'menu_balance' in _flat(with_money) and 'menu_balance' in _flat(paid_before)


def test_active_subscriber_gets_support_next_to_info_and_no_promocode():
    sub = SimpleNamespace(is_trial=False, traffic_limit_gb=0, tariff_id=2, id=1)
    kb = get_main_menu_keyboard(
        has_had_paid_subscription=True, has_active_subscription=True, subscription_is_active=True, subscription=sub
    )
    assert ['menu_support', 'menu_info'] in _callbacks(kb)
    assert 'menu_promocode' not in _flat(kb)


def test_support_row_collapses_to_info_alone_when_support_is_off(monkeypatch):
    monkeypatch.setattr(settings, 'SUPPORT_MENU_ENABLED', False, raising=False)
    sub = SimpleNamespace(is_trial=False, traffic_limit_gb=0, tariff_id=2, id=1)
    kb = get_main_menu_keyboard(
        has_had_paid_subscription=True, has_active_subscription=True, subscription_is_active=True, subscription=sub
    )
    assert 'menu_support' not in _flat(kb) and 'menu_info' in _flat(kb)


async def test_free_trial_is_activated_in_one_tap(monkeypatch):
    from app.handlers.subscription import purchase

    activate = AsyncMock()
    monkeypatch.setattr(purchase, 'activate_trial', activate)
    user = MagicMock(language='ru', auth_type='telegram')
    user.is_trial_already_used.return_value = False
    callback = MagicMock(message=MagicMock(edit_text=AsyncMock()), answer=AsyncMock())
    monkeypatch.setattr(settings, 'TRIAL_PAYMENT_ENABLED', False, raising=False)
    await purchase.show_trial_offer(callback, user, MagicMock())
    activate.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()  # экрана «Активировать?» больше нет


async def test_paid_trial_still_shows_the_offer_screen(monkeypatch):
    from app.handlers.subscription import purchase
    from app.services import trial_activation_service

    activate = AsyncMock()
    monkeypatch.setattr(purchase, 'activate_trial', activate)
    monkeypatch.setattr(trial_activation_service, 'get_trial_activation_charge_amount', lambda: 9900)
    user = MagicMock(language='ru', auth_type='telegram')
    user.is_trial_already_used.return_value = False
    callback = MagicMock(message=MagicMock(edit_text=AsyncMock()), answer=AsyncMock())
    await purchase.show_trial_offer(callback, user, MagicMock())
    activate.assert_not_awaited()
    callback.message.edit_text.assert_awaited()  # платный пробный период показывает экран с ценой
