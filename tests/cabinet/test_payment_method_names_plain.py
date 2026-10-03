"""Названия способов пополнения — без эмодзи в боте и кабинете (владелец: они лишние)."""

import json
import re

import pytest

from app.utils.miniapp_buttons import strip_leading_emoji


EMOJI = re.compile('[\U0001f000-\U0001faff☀-➿⬀-⯿️]')
NAME_KEY = re.compile(
    r'^PAYMENT_(METHOD_[A-Z0-9_]+|CARD_[A-Z0-9_]+|PLATEGA(_M\d+)?|CRYPTOBOT|HELEKET|XROCKET|'
    r'TELEGRAM_STARS|RIOPAY|CLOUDPAYMENTS|FREEKASSA|SBP_YOOKASSA|VIA_SUPPORT)$'
)
NOT_A_NAME = re.compile(r'ERROR|FAILED|RETURN|TITLE|CHARGE|SUCCESS|PROMPT|HEADER|DESCRIPTION|TEXT|INFO|HINT')


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_method_names_have_no_emoji(lang):
    with open(f'app/localization/locales/{lang}.json', encoding='utf-8') as fh:
        data = json.load(fh)
    offenders = {
        key: value
        for key, value in data.items()
        if isinstance(value, str) and NAME_KEY.match(key) and not NOT_A_NAME.search(key) and EMOJI.search(value)
    }
    assert not offenders


def test_api_helper_strips_the_leading_emoji():
    assert strip_leading_emoji('💳 Карта / СБП') == 'Карта / СБП'
    assert strip_leading_emoji('Карта / СБП') == 'Карта / СБП'
