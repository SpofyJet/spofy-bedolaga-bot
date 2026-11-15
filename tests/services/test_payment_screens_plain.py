"""Способы оплаты на кнопках — со значком, который бот превращает в премиум-иконку.

Владелец 30.10 вернул способам оплаты значки: 💳 карта / СБП, ⭐ Stars, ⚡ СБП (WATA),
🪙 крипта, 🛟 «Другие способы». Эмодзи в начале названия бот заменяет иконкой
icon_custom_emoji_id (app/keyboards/button_icons.py), поэтому ошибка — это эмодзи,
для которого иконки нет (на кнопке останется обычный), и сырой тег <tg-emoji>:
кнопки HTML не понимают. Заголовки экранов оплаты — по-прежнему без эмодзи перед
названием способа.
"""

import json
import re
from pathlib import Path

import pytest

from app.config import Settings, settings
from app.keyboards.button_icons import _icon_for
from app.keyboards.inline import (
    get_payment_methods_keyboard,
)


EMOJI = '[\U0001f000-\U0001faff☀-➿⬀-⯿️]'
BUTTON_NAME_KEYS = re.compile(
    r'^(PAYMENT_(CARD_[A-Z0-9_]+|PLATEGA(_M\d+)?|CRYPTOBOT|PAY2328|XROCKET|TELEGRAM_STARS|VIA_SUPPORT)'
    r'|TOP_UP_STARS|WATA_PAY_BUTTON|PLATEGA_PAY_BUTTON)$'
)
SCREEN_TITLES = ['WATA_PAYMENT_INSTRUCTIONS', 'WATA_TOPUP_PROMPT']


def _data(lang):
    return json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))


def _button_problem(label: str) -> str | None:
    if '<tg-emoji' in label:
        return 'сырой тег <tg-emoji> на кнопке'
    if not re.search(EMOJI, label):
        return None
    found = _icon_for(label)
    if found is None or re.search(EMOJI, found[0]):
        return 'эмодзи без премиум-иконки'
    return None


@pytest.mark.parametrize('lang', ['ru', 'en'])
def test_payment_button_names_use_premium_icons(lang):
    data = _data(lang)
    offenders = {
        key: (value, problem)
        for key, value in data.items()
        if isinstance(value, str) and BUTTON_NAME_KEYS.match(key) and (problem := _button_problem(value))
    }
    assert not offenders


@pytest.mark.parametrize('lang', ['ru', 'en'])
def test_payment_screen_titles_start_without_emoji(lang):
    data = _data(lang)
    offenders = {key: data[key] for key in SCREEN_TITLES if key in data and re.match(r'^(<b>)?' + EMOJI, data[key])}
    assert not offenders


@pytest.mark.parametrize('lang', ['ru', 'en'])
def test_every_method_button_gets_a_premium_icon(monkeypatch, lang):
    for name in (
        'is_platega_enabled',
        'is_wata_enabled',
        'is_cryptobot_enabled',
        'is_xrocket_enabled',
        'is_pay2328_enabled',
    ):
        monkeypatch.setattr(Settings, name, lambda self: True)
    monkeypatch.setattr(Settings, 'get_platega_active_methods', lambda self: [2, 12])
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_ENABLED', True)

    keyboard = get_payment_methods_keyboard(0, lang)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert any('Platega' in label for label in labels) and any('CryptoBot' in label for label in labels)
    for label in labels:
        assert _icon_for(label) is not None, label
        assert _button_problem(label) is None, label


@pytest.mark.parametrize('name', ['cryptobot', 'xrocket', 'pay2328', 'platega', 'wata', 'stars'])
def test_screen_titles_have_no_leading_emoji(name):
    source = Path(f'app/handlers/balance/{name}.py').read_text(encoding='utf-8')
    assert not re.search(
        r"""['"]""" + EMOJI + r'+ (<b>Оплата через|Оплатить через|<b>Telegram Stars|Безопасная оплата)', source
    )
