"""Экран «Подписка оформлена» ведёт к подключению одним нажатием."""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.handlers.subscription.tariff_purchase import _connect_rows
from app.localization.texts import get_texts


def _sub(url='https://sub.spofyltd.ru/abc123'):
    return SimpleNamespace(id=1, subscription_url=url, subscription_crypto_link=None)


def test_link_mode_opens_the_subscription_page_directly(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'link')
    (row,) = _connect_rows(_sub(), get_texts('ru'))
    assert row[0].url == 'https://sub.spofyltd.ru/abc123'
    assert 'Подключить' in row[0].text


def test_other_modes_use_the_bot_connect_screen(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'guide')
    (row,) = _connect_rows(_sub(), get_texts('ru'))
    assert row[0].callback_data == 'subscription_connect'


def test_link_mode_without_a_link_falls_back_to_the_guide(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECT_BUTTON_MODE', 'link')
    (row,) = _connect_rows(_sub(url=None), get_texts('ru'))
    assert row[0].callback_data == 'subscription_connect'


def test_no_subscription_no_button():
    assert _connect_rows(None, get_texts('ru')) == []


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_success_text_keeps_its_placeholders(lang):
    text = get_texts(lang).TARIFF_PURCHASE_SUCCESS
    text.format(name='x', traffic='x', devices=1, period='x', price='x')
