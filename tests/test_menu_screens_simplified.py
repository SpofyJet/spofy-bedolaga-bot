"""Экраны второго уровня без лишних шагов: поддержка на главной, устройства сразу, парные ряды."""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.keyboards import inline


def _cbs(markup):
    return [[b.callback_data or ('url' if b.url else 'webapp') for b in row] for row in markup.inline_keyboard]


def _flat(markup):
    return [c for row in _cbs(markup) for c in row]


@pytest.fixture(autouse=True)
def _bot_menu(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)


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


def test_paid_subscription_screen_opens_devices_directly(monkeypatch):
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs', raising=False)
    monkeypatch.setattr(settings, 'SUBSCRIPTION_REVOKE_ENABLED', True, raising=False)
    kb = inline.get_subscription_keyboard('ru', True, False, _paid_sub())
    cbs = _cbs(kb)
    flat = _flat(kb)
    assert 'subscription_settings' not in flat  # прослойка «Настройки» убрана
    assert ['subscription_manage_devices', 'instant_switch'] in cbs
    assert ['subscription_autopay', 'subscription_revoke'] in cbs


def test_support_screen_starts_with_direct_chat_and_pairs_tickets(monkeypatch):
    monkeypatch.setattr(settings, 'SUPPORT_USERNAME', '@spofysup', raising=False)
    rows = _cbs(inline.get_support_keyboard('ru'))
    assert rows[0] == ['url']
    assert ['create_ticket', 'my_tickets'] in rows


def test_referral_screen_uses_paired_rows(monkeypatch):
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ENABLED', True, raising=False)
    rows = _cbs(inline.get_referral_keyboard('ru', share_url='https://t.me/x'))
    assert ['referral_show_qr', 'referral_list'] in rows
    assert ['referral_analytics', 'referral_withdrawal'] in rows
    assert len(rows) <= 6
