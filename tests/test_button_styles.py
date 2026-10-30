"""Нативные цвета кнопок (Bot API button styles): success — главное действие,
danger — разрушительные, без стиля — вторичное."""

from types import SimpleNamespace

import app.keyboards.inline as kb


def _callbacks(markup) -> dict[str, object]:
    return {
        btn.callback_data: btn.style
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    }


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
            is_daily=False,
        ),
        traffic_limit_gb=100,
        end_date=None,
        is_daily_paused=False,
        autopay_enabled=False,
    )


def _patch_subscription_screen(monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(Settings, 'is_tariffs_mode', lambda self: True)
    monkeypatch.setattr(Settings, 'is_multi_tariff_enabled', lambda self: True)
    monkeypatch.setattr(kb.settings, 'CONNECT_BUTTON_MODE', 'link')
    monkeypatch.setattr(kb, 'get_display_subscription_link', lambda sub: 'https://example.com/sub')


def test_confirm_keyboard_styles():
    styles = _callbacks(kb.get_subscription_confirm_keyboard('ru'))
    assert styles['subscription_confirm'] == 'success'
    assert styles['checkout_toggle_autopay'] is None
    assert styles['subscription_cancel'] is None


def test_clear_saved_cart_is_danger():
    styles = _callbacks(kb.get_subscription_confirm_keyboard_with_cart('ru'))
    assert styles['clear_saved_cart'] == 'danger'
    assert styles['subscription_confirm'] == 'success'
    assert styles['checkout_toggle_autopay'] is None


def test_subscription_screen_main_actions(monkeypatch):
    _patch_subscription_screen(monkeypatch)
    markup = kb.get_subscription_keyboard(
        'ru', has_subscription=True, is_trial=False, subscription=_fake_sub('active')
    )
    styles = _callbacks(markup)
    connect = next(
        btn for row in markup.inline_keyboard for btn in row if 'Подключиться' in (btn.text or '')
    )
    assert connect.style == 'success'
    assert styles['subscription_extend'] == 'success'
    assert styles['subscription_autopay'] is None
    assert styles['back_to_menu'] is None


def test_balance_keyboard_topup_success():
    styles = _callbacks(kb.get_balance_keyboard('ru'))
    assert styles['balance_topup'] == 'success'


def test_devices_management_styles():
    pagination = SimpleNamespace(page=1, total_pages=1, has_prev=False, prev_page=1, has_next=False, next_page=1)
    markup = kb.get_devices_management_keyboard([], pagination, 'ru')
    styles = _callbacks(markup)
    assert styles['reset_all_devices'] == 'danger'
    assert styles['subscription_settings'] is None


def test_referral_secondary_buttons_plain():
    markup = kb.get_referral_keyboard('ru')
    styles = _callbacks(markup)
    assert styles['referral_create_invite'] is None
    assert styles['referral_show_qr'] is None
    assert styles['referral_list'] is None
    assert styles['referral_analytics'] is None
