"""Экраны оплаты активных способов (Platega, WATA, Stars, CryptoBot, xRocket, Heleket) — без эмодзи у названий."""

import json
import re
from pathlib import Path

import pytest


EMOJI = '[\U0001f000-\U0001faff☀-➿⬀-⯿️]'
TITLE = re.compile(
    r"""['"]"""
    + EMOJI
    + r'+ (<b>Оплата через|Оплатить через|<b>Статус платежа WATA|<b>Telegram Stars|Безопасная оплата)'
)
KEYS = ['TOP_UP_STARS', 'WATA_PAYMENT_INSTRUCTIONS', 'WATA_TOPUP_PROMPT', 'WATA_PAY_BUTTON', 'PLATEGA_PAY_BUTTON']


@pytest.mark.parametrize('name', ['platega', 'wata', 'stars', 'cryptobot', 'xrocket', 'heleket'])
def test_screen_titles_have_no_leading_emoji(name):
    source = Path(f'app/handlers/balance/{name}.py').read_text(encoding='utf-8')
    assert not TITLE.search(source)


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_method_keys_have_no_leading_emoji(lang):
    data = json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))
    for key in KEYS:
        if key in data:
            assert not re.match(EMOJI, data[key]), key


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_methods_screen_title_has_no_emoji(lang):
    data = json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))
    assert not re.search(EMOJI, data['PAYMENT_METHODS_TITLE'])
