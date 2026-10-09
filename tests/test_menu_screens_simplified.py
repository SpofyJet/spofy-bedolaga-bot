"""Экраны второго уровня без лишних шагов: поддержка на главной, устройства и их количество сразу на подписке."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.keyboards import inline


MAX_PAIRED_LABEL = 15  # длиннее в паре на телефоне обрезается: человек не видит, что за кнопка


def _cbs(markup):
    return [[b.callback_data or ('url' if b.url else 'webapp') for b in row] for row in markup.inline_keyboard]


def _flat(markup):
    return [c for row in _cbs(markup) for c in row]


def _assert_pairs_fit(markup):
    for row in markup.inline_keyboard:
        if len(row) > 1:
            for button in row:
                assert len(button.text) <= MAX_PAIRED_LABEL, f'«{button.text}» не влезает в пару на телефоне'


@pytest.fixture(autouse=True)
def _bot_menu(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)
    monkeypatch.setattr(settings, 'SUPPORT_MENU_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'TRIAL_DURATION_DAYS', 2, raising=False)
    monkeypatch.setattr(settings, 'TRIAL_DISABLED_FOR', 'none', raising=False)


def test_info_menu_no_longer_duplicates_support(monkeypatch):
    monkeypatch.setattr(settings, 'LANGUAGE_SELECTION_ENABLED', True, raising=False)
    flat = _flat(inline.get_info_menu_keyboard('ru', show_faq=True, show_rules=True))
    assert 'menu_support' not in flat
    assert 'menu_language' in flat  # язык при регистрации не спрашиваем, но сменить его можно здесь


def test_info_menu_keeps_support_in_cabinet_mode(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'cabinet', raising=False)
    assert 'menu_support' in _flat(inline.get_info_menu_keyboard('ru', show_faq=True))


def _paid_sub(**kw):
    tariff = SimpleNamespace(
        id=2, is_daily=False, is_free=False, name='T', traffic_limit_gb=0, device_limit=3,
        can_topup_traffic=lambda: False, device_price_kopeks=5000,
    )  # fmt: skip
    base = dict(
        id=1, tariff_id=2, tariff=tariff, is_trial=False, traffic_limit_gb=0, actual_status='active',
        is_active=True, subscription_url=None, subscription_crypto_link=None, remnawave_short_uuid=None,
        is_daily_paused=False, connected_squads=[],
    )  # fmt: skip
    base.update(kw)
    return SimpleNamespace(**base)


def test_paid_subscription_screen_has_devices_and_their_count(monkeypatch):
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs', raising=False)
    monkeypatch.setattr(settings, 'SUBSCRIPTION_REVOKE_ENABLED', True, raising=False)
    kb = inline.get_subscription_keyboard('ru', True, False, _paid_sub())
    cbs = _cbs(kb)
    assert 'subscription_settings' not in _flat(kb)  # прослойка «Настройки» убрана
    assert ['subscription_manage_devices', 'instant_switch'] in cbs
    assert ['subscription_change_devices'] in cbs  # количество устройств видно сразу, без обходных путей
    assert ['subscription_autopay', 'subscription_revoke'] in cbs
    _assert_pairs_fit(kb)


def test_devices_count_hidden_when_tariff_cannot_sell_devices(monkeypatch):
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs', raising=False)
    sub = _paid_sub()
    sub.tariff.device_price_kopeks = 0
    assert 'subscription_change_devices' not in _flat(inline.get_subscription_keyboard('ru', True, False, sub))


async def test_old_settings_back_button_lands_on_the_subscription_screen(monkeypatch):
    """«Назад» из устройств и перевыпуска ведёт на subscription_settings: на тарифах это экран подписки."""
    from app.database.crud import tariff as tariff_crud
    from app.handlers.subscription import purchase

    shown = AsyncMock()
    monkeypatch.setattr(purchase, 'show_subscription_info', shown)
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs', raising=False)
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False, raising=False)
    monkeypatch.setattr(tariff_crud, 'get_tariff_by_id', AsyncMock(return_value=SimpleNamespace(id=2)))
    user = MagicMock(language='ru', subscription=SimpleNamespace(is_trial=False, tariff_id=2))
    callback = MagicMock(answer=AsyncMock(), message=MagicMock(edit_text=AsyncMock()))
    await purchase.handle_subscription_settings(callback, user, MagicMock())
    shown.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()


def test_support_screen_starts_with_direct_chat(monkeypatch):
    monkeypatch.setattr(settings, 'SUPPORT_USERNAME', '@spofysup', raising=False)
    rows = _cbs(inline.get_support_keyboard('ru'))
    assert rows[0] == ['url']
    assert ['create_ticket'] in rows and ['my_tickets'] in rows


def test_referral_screen_is_one_button_per_row_and_readable(monkeypatch):
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ENABLED', True, raising=False)
    kb = inline.get_referral_keyboard('ru', share_url='https://t.me/x')
    assert all(len(row) == 1 for row in kb.inline_keyboard)  # парные длинные подписи на телефоне не видны
    assert {'referral_show_qr', 'referral_list', 'referral_analytics', 'referral_withdrawal'} <= set(_flat(kb))


@pytest.mark.parametrize(
    ('active', 'trial', 'balance', 'paid_before'),
    [(False, False, 0, False), (True, True, 0, False), (True, False, 0, True), (False, False, 5000, True)],
)
def test_main_menu_pairs_fit_a_phone(active, trial, balance, paid_before):
    sub = SimpleNamespace(is_trial=trial, traffic_limit_gb=0, tariff_id=2, id=1) if active else None
    kb = inline.get_main_menu_keyboard(
        has_had_paid_subscription=paid_before,
        has_active_subscription=active,
        subscription_is_active=active,
        subscription=sub,
        balance_kopeks=balance,
    )
    _assert_pairs_fit(kb)


def test_trial_user_without_money_can_still_reach_promocode():
    trial = SimpleNamespace(is_trial=True, traffic_limit_gb=0, tariff_id=None, id=1)
    kb = inline.get_main_menu_keyboard(
        has_had_paid_subscription=False, has_active_subscription=True, subscription_is_active=True,
        subscription=trial, balance_kopeks=0,
    )  # fmt: skip
    flat = _flat(kb)
    assert 'menu_promocode' in flat and 'menu_balance' not in flat


def test_paying_subscriber_always_sees_balance_even_at_zero():
    paid = SimpleNamespace(is_trial=False, traffic_limit_gb=0, tariff_id=2, id=1)
    kb = inline.get_main_menu_keyboard(
        has_had_paid_subscription=False, has_active_subscription=True, subscription_is_active=True,
        subscription=paid, balance_kopeks=0,
    )  # fmt: skip
    flat = _flat(kb)
    assert 'menu_balance' in flat and 'menu_promocode' not in flat
