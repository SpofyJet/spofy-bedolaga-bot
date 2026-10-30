"""UX-редизайн меню: регрессионный тест — дубль «Докупить трафик» на экране
подписки убран (одна кнопка максимум)."""

from __future__ import annotations

from types import SimpleNamespace

import app.keyboards.inline as kb


def _callbacks(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


def _fake_sub(actual_status: str = 'active') -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        actual_status=actual_status,
        status=actual_status,
        tariff_id=7,
        tariff=SimpleNamespace(
            can_topup_traffic=lambda: True,
            is_free=False,
            device_price_kopeks=0,
        ),
        traffic_limit_gb=100,
        end_date=None,
        is_daily_paused=False,
        autopay_enabled=False,
    )


def _patch_tariffs_mode(monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(Settings, 'is_tariffs_mode', lambda self: True)
    monkeypatch.setattr(Settings, 'is_multi_tariff_enabled', lambda self: True)
    monkeypatch.setattr(kb, 'get_display_subscription_link', lambda sub: None)


def test_active_sub_single_traffic_button(monkeypatch):
    _patch_tariffs_mode(monkeypatch)
    markup = kb.get_subscription_keyboard(
        'ru', has_subscription=True, is_trial=False, subscription=_fake_sub('active')
    )
    assert _callbacks(markup).count('buy_traffic') == 1


def test_expired_sub_single_traffic_button(monkeypatch):
    _patch_tariffs_mode(monkeypatch)
    markup = kb.get_subscription_keyboard(
        'ru', has_subscription=True, is_trial=False, subscription=_fake_sub('expired')
    )
    assert _callbacks(markup).count('buy_traffic') <= 1


def test_secondary_actions_one_per_row():
    markup = kb.get_referral_keyboard('ru')
    assert all(len(row) == 1 for row in markup.inline_keyboard)
    callbacks = _callbacks(markup)
    assert callbacks[:4] == ['referral_create_invite', 'referral_show_qr', 'referral_list', 'referral_analytics']
