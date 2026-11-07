"""Кнопка «🎡 Колесо призов · N спинов» в главном меню: видна, только пока есть непрокрученный спин."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.keyboards import inline
from app.keyboards.inline import _spins_word, _wheel_spins_for_menu, get_main_menu_keyboard


@pytest.fixture(autouse=True)
def _bot_menu(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://web.spofyltd.ru', raising=False)


def _wheel_buttons(markup):
    return [b for row in markup.inline_keyboard for b in row if b.web_app and b.web_app.url.endswith('/wheel')]


def test_no_spins_no_button():
    assert _wheel_buttons(get_main_menu_keyboard(has_active_subscription=True, subscription_is_active=True)) == []


def test_spin_shows_webapp_button_to_wheel_above_referrals(monkeypatch):
    monkeypatch.setattr(settings, 'REFERRAL_PROGRAM_ENABLED', True, raising=False)
    kb = get_main_menu_keyboard(has_active_subscription=True, subscription_is_active=True, wheel_spins_available=2)
    [button] = _wheel_buttons(kb)
    assert button.web_app.url == 'https://web.spofyltd.ru/wheel'
    assert button.text.endswith('Колесо призов · 2 спина')
    flat = [b for row in kb.inline_keyboard for b in row]
    referrals = [i for i, b in enumerate(flat) if b.callback_data == 'menu_referrals']
    if referrals:
        assert flat.index(button) < referrals[0]


def test_no_cabinet_url_no_button(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', '', raising=False)
    assert _wheel_buttons(get_main_menu_keyboard(wheel_spins_available=1)) == []


@pytest.mark.parametrize(
    ('count', 'word'),
    [(1, 'спин'), (2, 'спина'), (4, 'спина'), (5, 'спинов'), (11, 'спинов'), (12, 'спинов'), (21, 'спин'), (22, 'спина')],
)
def test_spins_word(count, word):
    assert _spins_word(count) == word


async def test_spins_for_menu_counts_only_when_topup_spins_enabled(monkeypatch):
    from app.database.crud import wheel as wheel_crud
    from app.services import wheel_service as ws

    user = SimpleNamespace(id=7)
    config = SimpleNamespace(is_enabled=True, topup_spins_enabled=True)
    monkeypatch.setattr(wheel_crud, 'get_wheel_config', AsyncMock(return_value=config))
    monkeypatch.setattr(
        ws.wheel_service, 'get_free_spin_state', AsyncMock(return_value=SimpleNamespace(available=3))
    )
    assert await _wheel_spins_for_menu(object(), user) == 3

    config.topup_spins_enabled = False
    assert await _wheel_spins_for_menu(object(), user) == 0


async def test_spins_for_menu_never_breaks_the_menu(monkeypatch):
    from app.database.crud import wheel as wheel_crud

    monkeypatch.setattr(wheel_crud, 'get_wheel_config', AsyncMock(side_effect=RuntimeError('db down')))
    assert await _wheel_spins_for_menu(object(), SimpleNamespace(id=7)) == 0
    assert await _wheel_spins_for_menu(object(), None) == 0
    assert inline  # module imported
