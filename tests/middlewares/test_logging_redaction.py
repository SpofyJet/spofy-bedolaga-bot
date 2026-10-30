"""Лог входящих апдейтов не хранит токены входа, коды подарков и номера карт."""

from __future__ import annotations

from app.middlewares.logging import _redact


def test_webauth_token_is_masked() -> None:
    token = 'Q3xY9kLmN0pRsT2uVwXyZ4aBcDeFgHiJ'
    assert token not in _redact(f'/start webauth_{token}')
    assert token not in _redact(f'webauth_confirm:{token}')


def test_gift_code_is_masked() -> None:
    code = 'GIFT_' + 'a1B2c3D4e5' * 5
    assert code[5:] not in _redact(f'/start {code}')


def test_card_number_is_masked() -> None:
    assert '4276' not in _redact('Сбер 4276 1234 5678 9012')


def test_regular_text_and_short_callbacks_are_kept() -> None:
    assert _redact('/start') == '/start'
    assert _redact('menu_balance') == 'menu_balance'
    assert _redact('Привет, хочу купить на 3 месяца') == 'Привет, хочу купить на 3 месяца'
    assert _redact(None) is None


def test_long_callback_names_are_kept() -> None:
    assert _redact('subscription_settings_menu_back') == 'subscription_settings_menu_back'
    assert _redact('admin_users_page_12_filter_active') == 'admin_users_page_12_filter_active'
