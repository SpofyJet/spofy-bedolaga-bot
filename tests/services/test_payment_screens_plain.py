"""Названия платёжных систем — без эмодзи нигде в боте (владелец: «нигде не должно быть эмодзи»)."""

import json
import re
from pathlib import Path

import pytest

from app.config import Settings, settings
from app.keyboards.inline import get_cryptobot_payment_keyboard, get_payment_methods_keyboard
from app.localization.texts import get_texts


EMOJI = '[\U0001f000-\U0001faff☀-➿⬀-⯿️]'
NAME_KEYS = re.compile(
    r'^PAYMENT_(METHOD_[A-Z0-9_]+|CARD_[A-Z0-9_]+|PLATEGA(_M\d+)?|CRYPTOBOT|HELEKET|XROCKET|TELEGRAM_STARS|RIOPAY|'
    r'CLOUDPAYMENTS|FREEKASSA|SBP_YOOKASSA|VIA_SUPPORT|METHODS_TITLE)$'
)
NOT_A_NAME = re.compile(r'ERROR|FAILED|RETURN|CHARGE|SUCCESS|PROMPT_|HEADER|DESCRIPTION|TEXT|INFO|HINT')
EXTRA = ['TOP_UP_STARS', 'WATA_PAYMENT_INSTRUCTIONS', 'WATA_TOPUP_PROMPT', 'WATA_PAY_BUTTON', 'PLATEGA_PAY_BUTTON']


def _data(lang):
    return json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_payment_names_have_no_emoji(lang):
    data = _data(lang)
    offenders = {
        key: value
        for key, value in data.items()
        if isinstance(value, str) and NAME_KEYS.match(key) and not NOT_A_NAME.search(key) and re.search(EMOJI, value)
    }
    # Экранные тексты с описанием оплаты: название способа в начале — без эмодзи.
    offenders.update({key: data[key] for key in EXTRA if key in data and re.match(r'^(<b>)?' + EMOJI, data[key])})
    assert not offenders


def test_methods_keyboard_has_no_emoji_except_back(monkeypatch):
    for name in (
        'is_platega_enabled',
        'is_wata_enabled',
        'is_cryptobot_enabled',
        'is_xrocket_enabled',
        'is_heleket_enabled',
    ):
        monkeypatch.setattr(Settings, name, lambda self: True)
    monkeypatch.setattr(Settings, 'get_platega_active_methods', lambda self: [2, 12])
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_ENABLED', True)

    keyboard = get_payment_methods_keyboard(0, 'ru')
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert any('Platega' in label for label in labels) and any('CryptoBot' in label for label in labels)
    for label in labels:
        if label != get_texts('ru').BACK:
            assert not re.search(EMOJI, label), label


def test_crypto_payment_keyboard_has_no_emoji_in_its_buttons():
    keyboard = get_cryptobot_payment_keyboard('inv1', 1, 1.0, 'USDT', 'https://t.me/x', 'ru')
    for row in keyboard.inline_keyboard:
        for button in row:
            assert not re.search(EMOJI, button.text), button.text


@pytest.mark.parametrize('name', ['cryptobot', 'xrocket', 'heleket', 'platega', 'wata', 'stars'])
def test_screen_titles_have_no_leading_emoji(name):
    source = Path(f'app/handlers/balance/{name}.py').read_text(encoding='utf-8')
    assert not re.search(
        r"""['"]""" + EMOJI + r'+ (<b>Оплата через|Оплатить через|<b>Telegram Stars|Безопасная оплата)', source
    )
