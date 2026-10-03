"""Эмодзи у способов оплаты: у карт, СБП и Stars остаются, у криптовалют (CryptoBot, xRocket, Heleket) убраны."""

import json
import re
from pathlib import Path

import pytest

from app.keyboards.inline import get_cryptobot_payment_keyboard
from app.localization.texts import get_texts


EMOJI = '[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f]'
CRYPTO_KEYS = re.compile(r'CRYPTO|HELEKET|XROCKET|PLATEGA_M13')
METHOD_NAME_KEYS = re.compile(
    r'^PAYMENT_(METHOD_[A-Z0-9_]+_NAME|PLATEGA(_M\d+)?|CRYPTOBOT|HELEKET|XROCKET|TELEGRAM_STARS)$'
)


def _data(lang):
    return json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_crypto_method_names_have_no_emoji(lang):
    for key, value in _data(lang).items():
        if METHOD_NAME_KEYS.match(key) and CRYPTO_KEYS.search(key):
            assert not re.search(EMOJI, value), key


def test_card_and_sbp_names_keep_their_emoji():
    data = _data('ru')
    assert data['PAYMENT_PLATEGA_M2'].startswith('💳')
    assert data['PAYMENT_METHOD_SBP'].startswith('🏦')
    assert data['PAYMENT_METHODS_TITLE'].startswith('💳')


def test_crypto_payment_keyboard_has_no_emoji_in_its_buttons():
    keyboard = get_cryptobot_payment_keyboard('inv1', 1, 1.0, 'USDT', 'https://t.me/x', 'ru')
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels
    for label in labels:
        if label != get_texts('ru').BACK:
            assert not re.search(EMOJI, label), label


@pytest.mark.parametrize('name', ['cryptobot', 'xrocket', 'heleket'])
def test_crypto_screen_buttons_are_plain(name):
    source = Path(f'app/handlers/balance/{name}.py').read_text(encoding='utf-8')
    assert not re.search(r"text='" + EMOJI, source)
