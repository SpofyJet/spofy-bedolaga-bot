"""Сбой создания платежа: другие способы на ту же сумму; CryptoBot в напоминании о брошенной оплате."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.activation_funnel_service import _cryptobot_payload_kopeks
from app.utils import payment_fallback


def _keyboard(*methods):
    rows = [[InlineKeyboardButton(text=m, callback_data=f'topup_amount|{m}|31500')] for m in methods]
    rows.append([InlineKeyboardButton(text='назад', callback_data='balance_topup')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def test_failed_provider_is_removed_and_others_stay(monkeypatch):
    monkeypatch.setattr(
        'app.keyboards.inline.get_payment_methods_keyboard',
        lambda amount, lang: _keyboard('platega', 'platega_m2', 'wata', 'cryptobot'),
    )
    markup = payment_fallback.fallback_methods_keyboard(31500, 'ru', 'platega')
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks == ['topup_amount|wata|31500', 'topup_amount|cryptobot|31500']  # без Platega и без навигации


def test_no_alternatives_returns_none(monkeypatch):
    monkeypatch.setattr('app.keyboards.inline.get_payment_methods_keyboard', lambda amount, lang: _keyboard('platega'))
    assert payment_fallback.fallback_methods_keyboard(31500, 'ru', 'platega') is None


def test_text_has_amount():
    assert '315 ₽' in payment_fallback.fallback_text('ru', 31500)


def test_cryptobot_payload_gives_kopeks():
    assert _cryptobot_payload_kopeks('balance_401_315000') == 315000
    assert _cryptobot_payload_kopeks('balance_122_10000') == 10000
    assert _cryptobot_payload_kopeks(None) == 0
    assert _cryptobot_payload_kopeks('garbage') == 0
