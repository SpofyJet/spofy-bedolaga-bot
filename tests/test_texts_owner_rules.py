"""Тексты бота против правил владельца: «обращение», а не «тикет в панели»; без слова «лимит» про устройства."""

import json
from pathlib import Path

import pytest


LOCALES = Path(__file__).resolve().parents[1] / 'app/localization/locales'


def _load(language: str) -> dict[str, str]:
    return json.loads((LOCALES / f'{language}.json').read_text(encoding='utf-8'))


def test_outdated_message_text_speaks_of_request_not_panel() -> None:
    text = _load('ru')['MESSAGE_TOO_OLD'].lower()
    assert 'обращение' in text
    assert 'тикет' not in text
    assert 'панел' not in text
    assert 'panel' not in _load('en')['MESSAGE_TOO_OLD'].lower()


@pytest.mark.parametrize('key', ['DEVICES_LIMIT_EXCEEDED', 'DEVICES_LIMIT_EXCEEDED_DETAIL'])
def test_device_cap_text_has_no_word_limit(key: str) -> None:
    assert 'лимит' not in _load('ru')[key].lower()
    assert 'limit exceeded' not in _load('en')[key].lower()
    for language in ('ru', 'en'):
        assert '{limit}' in _load(language)[key]
    for language in ('ru', 'en'):
        detail = _load(language)['DEVICES_LIMIT_EXCEEDED_DETAIL']
        assert '{current}' in detail
        assert '{adding}' in detail


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_texts_of_removed_payment_providers_are_gone(language: str) -> None:
    keys = _load(language)
    dead = [
        key
        for key in keys
        if key.startswith('CASHERA_')
        or 'CLOUDPAYMENTS' in key
        or key in {'REFERRAL_INVITE_MESSAGE', 'CHANGE_DEVICES_INFO'}
    ]
    assert dead == []
