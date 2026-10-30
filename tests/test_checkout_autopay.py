"""Автопродление в checkout классической покупки: клавиатуры, подписи, локали."""

import json
from pathlib import Path

from app.keyboards.inline import (
    get_subscription_confirm_keyboard,
    get_subscription_confirm_keyboard_with_cart,
)


def _callbacks(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]


def test_confirm_keyboard_row_order():
    markup = get_subscription_confirm_keyboard('ru')
    first_row = markup.inline_keyboard[0]
    assert len(first_row) == 1
    assert first_row[0].callback_data == 'subscription_confirm'
    assert _callbacks(markup) == ['subscription_confirm', 'checkout_toggle_autopay', 'subscription_cancel']


def test_toggle_label_differs_and_reads_on_off():
    on_markup = get_subscription_confirm_keyboard('ru', autopay_enabled=True)
    off_markup = get_subscription_confirm_keyboard('ru', autopay_enabled=False)
    on_label = on_markup.inline_keyboard[1][0].text
    off_label = off_markup.inline_keyboard[1][0].text
    assert on_label != off_label
    assert 'вкл' in on_label
    assert 'выкл' in off_label


def test_toggle_hidden_when_unavailable():
    markup = get_subscription_confirm_keyboard('ru', autopay_available=False)
    assert _callbacks(markup) == ['subscription_confirm', 'subscription_cancel']


def test_no_duplicate_callbacks():
    for markup in (
        get_subscription_confirm_keyboard('ru'),
        get_subscription_confirm_keyboard('ru', autopay_enabled=True),
        get_subscription_confirm_keyboard_with_cart('ru'),
        get_subscription_confirm_keyboard_with_cart('ru', autopay_enabled=True),
        get_subscription_confirm_keyboard('ru', autopay_available=False),
    ):
        callbacks = _callbacks(markup)
        assert len(callbacks) == len(set(callbacks)), callbacks


def test_confirm_with_cart_layout():
    markup = get_subscription_confirm_keyboard_with_cart('ru')
    assert len(markup.inline_keyboard[0]) == 1
    assert markup.inline_keyboard[0][0].callback_data == 'subscription_confirm'
    callbacks = _callbacks(markup)
    assert 'checkout_toggle_autopay' in callbacks
    assert 'clear_saved_cart' in callbacks
    assert callbacks[-1] == 'subscription_config_back'


def test_locale_keys_present_and_distinct():
    locales_dir = Path(__file__).parent.parent / 'app' / 'localization' / 'locales'
    for lang in ('ru', 'en', 'ua', 'fa', 'zh'):
        data = json.loads((locales_dir / f'{lang}.json').read_text())
        for key in (
            'CHECKOUT_AUTOPAY_BUTTON_ON',
            'CHECKOUT_AUTOPAY_BUTTON_OFF',
            'CHECKOUT_AUTOPAY_ON_NOTE',
            'CHECKOUT_AUTOPAY_OFF_NOTE',
        ):
            assert data.get(key), f'{lang}:{key} missing or empty'
        assert data['CHECKOUT_AUTOPAY_BUTTON_ON'] != data['CHECKOUT_AUTOPAY_BUTTON_OFF']
        assert data['CHECKOUT_AUTOPAY_ON_NOTE'] != data['CHECKOUT_AUTOPAY_OFF_NOTE']
