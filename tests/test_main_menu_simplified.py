"""Главное меню без лишнего: баланс только тем, у кого он нужен; промокод под рукой, поддержка — в «Инфо»."""

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


def test_new_user_has_no_empty_balance_but_has_promocode_and_info():
    kb = get_main_menu_keyboard(has_had_paid_subscription=False, has_active_subscription=False, balance_kopeks=0)
    flat = _flat(kb)
    assert 'menu_balance' not in flat
    assert flat[:2] == ['menu_trial', 'menu_buy']
    assert ['menu_promocode', 'menu_info'] in _callbacks(kb)


def test_saved_cart_is_the_first_cta_and_wins_over_checkout_draft():
    kb = get_main_menu_keyboard(show_resume_checkout=True, has_saved_cart=True)
    callbacks = _callbacks(kb)
    assert callbacks[0] == ['return_to_saved_cart']
    assert _flat(kb).count('return_to_saved_cart') == 1
    assert 'subscription_resume_checkout' not in _flat(kb)


def test_checkout_draft_is_the_first_cta_without_saved_cart():
    kb = get_main_menu_keyboard(show_resume_checkout=True, has_saved_cart=False)
    assert _callbacks(kb)[0] == ['subscription_resume_checkout']


def test_balance_stays_for_people_with_money_or_paid_history():
    with_money = get_main_menu_keyboard(
        has_had_paid_subscription=False, has_active_subscription=False, balance_kopeks=5000
    )
    paid_before = get_main_menu_keyboard(
        has_had_paid_subscription=True, has_active_subscription=False, balance_kopeks=0
    )
    assert 'menu_balance' in _flat(with_money) and 'menu_balance' in _flat(paid_before)


def test_active_subscriber_gets_info_alone_and_no_promocode(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    sub = SimpleNamespace(is_trial=False, traffic_limit_gb=0, tariff_id=2, id=1)
    kb = get_main_menu_keyboard(
        has_had_paid_subscription=True, has_active_subscription=True, subscription_is_active=True, subscription=sub
    )
    assert 'subscription_connect' in _flat(kb)
    assert 'menu_buy' not in _flat(kb)
    assert ['menu_info'] in _callbacks(kb)
    assert 'menu_support' not in _flat(kb)
    assert 'menu_promocode' not in _flat(kb)


def test_active_trial_keeps_connect_and_a_separate_purchase(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    sub = SimpleNamespace(is_trial=True, traffic_limit_gb=0, tariff_id=2, id=1)
    kb = get_main_menu_keyboard(
        has_had_paid_subscription=False, has_active_subscription=True, subscription_is_active=True, subscription=sub
    )
    flat = _flat(kb)
    assert 'subscription_connect' in flat
    assert 'menu_buy' in flat
    assert flat.index('subscription_connect') < flat.index('menu_buy')


@pytest.mark.parametrize('status', ['expired', 'disabled'])
def test_inactive_subscription_with_link_keeps_connect_and_purchase(monkeypatch, status):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    sub = SimpleNamespace(
        id=42,
        actual_status=status,
        is_trial=False,
        traffic_limit_gb=100,
        tariff_id=2,
        subscription_url='https://example.invalid/sub/42',
        subscription_crypto_link=None,
    )
    kb = get_main_menu_keyboard(
        has_had_paid_subscription=True,
        has_active_subscription=False,
        subscription_is_active=False,
        subscription=sub,
    )
    flat = _flat(kb)
    assert 'subscription_connect' in flat
    assert flat.count('menu_buy') == 1
    assert 'buy_traffic' not in flat


def test_expired_trial_with_link_does_not_duplicate_purchase(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    sub = SimpleNamespace(
        id=43,
        actual_status='expired',
        is_trial=True,
        traffic_limit_gb=0,
        tariff_id=2,
        subscription_url='https://example.invalid/sub/43',
        subscription_crypto_link=None,
    )
    kb = get_main_menu_keyboard(subscription=sub)
    flat = _flat(kb)
    assert 'subscription_connect' in flat
    assert flat.count('menu_buy') == 1


def test_inactive_subscription_without_link_has_no_dead_connect(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    sub = SimpleNamespace(
        id=44,
        actual_status='expired',
        is_trial=False,
        traffic_limit_gb=0,
        tariff_id=2,
        subscription_url=None,
        subscription_crypto_link=None,
    )
    kb = get_main_menu_keyboard(subscription=sub)
    flat = _flat(kb)
    assert 'subscription_connect' not in flat
    assert 'menu_buy' in flat


def test_inactive_multi_tariff_connect_targets_exact_subscription(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', True)
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs')
    sub = SimpleNamespace(
        id=45,
        actual_status='expired',
        is_trial=False,
        traffic_limit_gb=0,
        tariff_id=2,
        subscription_url='https://example.invalid/sub/45',
        subscription_crypto_link=None,
    )
    kb = get_main_menu_keyboard(subscription=sub)
    assert 'sl:45' in _flat(kb)
    assert 'subscription_connect' not in _flat(kb)


def test_support_is_not_in_main_menu_even_when_enabled(monkeypatch):
    # «Поддержка» живёт внутри «Инфо»; SUPPORT_MENU_ENABLED на главную её не возвращает.
    monkeypatch.setattr(settings, 'SUPPORT_MENU_ENABLED', True, raising=False)
    sub = SimpleNamespace(is_trial=False, traffic_limit_gb=0, tariff_id=2, id=1)
    kb = get_main_menu_keyboard(
        has_had_paid_subscription=True, has_active_subscription=True, subscription_is_active=True, subscription=sub
    )
    assert 'menu_support' not in _flat(kb) and 'menu_info' in _flat(kb)


async def test_pending_checkout_suppresses_only_random_menu_message(monkeypatch):
    from app.handlers import menu as menu_mod

    user = SimpleNamespace(id=123, full_name='User')
    texts = SimpleNamespace(
        MAIN_MENU='Hello {user_name}\n{subscription_status}\nChoose:',
        t=lambda key, default: default,
    )
    monkeypatch.setattr(menu_mod.settings, 'MULTI_TARIFF_ENABLED', True)
    monkeypatch.setattr(menu_mod.settings, 'SALES_MODE', 'tariffs')
    monkeypatch.setattr(menu_mod, '_get_multi_tariff_status', AsyncMock(return_value=('Active', '')))
    monkeypatch.setattr(menu_mod, 'build_promo_offer_hint', AsyncMock(return_value='Real promo'))
    monkeypatch.setattr(menu_mod, 'build_test_access_hint', AsyncMock(return_value=None))
    monkeypatch.setattr(menu_mod, 'has_subscription_checkout_draft', AsyncMock(return_value=True))
    monkeypatch.setattr(menu_mod, 'should_offer_checkout_resume', lambda user, draft: draft)
    random_message = AsyncMock(return_value='Random promo')
    monkeypatch.setattr(menu_mod, 'get_random_active_message', random_message)

    result = await menu_mod.get_main_menu_text(user, texts, AsyncMock())

    assert 'Real promo' in result
    assert 'Random promo' not in result
    random_message.assert_not_awaited()


async def test_random_menu_message_remains_without_pending_checkout(monkeypatch):
    from app.handlers import menu as menu_mod

    user = SimpleNamespace(id=123, full_name='User')
    texts = SimpleNamespace(
        MAIN_MENU='Hello {user_name}\n{subscription_status}\nChoose:',
        t=lambda key, default: default,
    )
    monkeypatch.setattr(menu_mod.settings, 'MULTI_TARIFF_ENABLED', True)
    monkeypatch.setattr(menu_mod.settings, 'SALES_MODE', 'tariffs')
    monkeypatch.setattr(menu_mod, '_get_multi_tariff_status', AsyncMock(return_value=('Active', '')))
    monkeypatch.setattr(menu_mod, 'build_promo_offer_hint', AsyncMock(return_value=None))
    monkeypatch.setattr(menu_mod, 'build_test_access_hint', AsyncMock(return_value=None))
    monkeypatch.setattr(menu_mod, 'has_subscription_checkout_draft', AsyncMock(return_value=False))
    monkeypatch.setattr(menu_mod, 'should_offer_checkout_resume', lambda user, draft: False)
    monkeypatch.setattr(menu_mod.user_cart_service, 'has_user_cart', AsyncMock(return_value=False))
    monkeypatch.setattr(menu_mod, 'get_random_active_message', AsyncMock(return_value='Random promo'))

    result = await menu_mod.get_main_menu_text(user, texts, AsyncMock())

    assert 'Random promo' in result


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
