"""После /start и регистрации — то же главное меню, что по «Назад в меню».

В start.py было шесть своих копий сборки клавиатуры: без кнопки сохранённой корзины, с флагами
подписки по первой подписке вместо всех, а одна копия брала кнопки конструктора даже в
текстовом режиме меню. Теперь все пути зовут ``build_main_menu_keyboard`` из handlers/menu.py.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.models import Subscription, SubscriptionStatus


def _sub(status: str, days: int) -> Subscription:
    return Subscription(status=status, is_trial=False, end_date=datetime.now(UTC) + timedelta(days=days))


def _user(subscriptions) -> SimpleNamespace:
    user = SimpleNamespace(
        id=7,
        telegram_id=700,
        language='ru',
        has_had_paid_subscription=True,
        balance_kopeks=0,
        subscriptions=subscriptions,
    )
    user.subscription = next((s for s in subscriptions if s.status == SubscriptionStatus.ACTIVE.value), None)
    return user


def test_start_has_no_own_copy_of_the_menu_keyboard():
    from app.handlers import start as start_mod

    source = inspect.getsource(start_mod)
    assert 'get_main_menu_keyboard_async(' not in source
    assert source.count('await _main_menu_keyboard(') == 6, 'все шесть путей /start и регистрации'


@pytest.mark.asyncio
async def test_start_keyboard_is_the_back_to_menu_keyboard(monkeypatch):
    from app.handlers import menu as menu_mod, start as start_mod

    builder = AsyncMock(return_value='KEYBOARD')
    monkeypatch.setattr(menu_mod, 'build_main_menu_keyboard', builder)
    user, db = object(), object()

    assert await start_mod._main_menu_keyboard(user, db) == 'KEYBOARD'
    builder.assert_awaited_once_with(user, db)


@pytest.mark.parametrize('text_mode', [False, True])
@pytest.mark.asyncio
async def test_start_menu_has_cart_button_all_subscriptions_and_respects_text_mode(monkeypatch, text_mode):
    """Корзина есть, первая подписка истекла, вторая активна — как у «Назад в меню»."""
    from app.config import settings
    from app.handlers import menu as menu_mod, start as start_mod

    keyboard_builder = AsyncMock(return_value='KEYBOARD')
    custom_buttons = AsyncMock(return_value=['CUSTOM'])
    monkeypatch.setattr(menu_mod, 'get_main_menu_keyboard_async', keyboard_builder)
    monkeypatch.setattr(menu_mod, 'has_resumable_cart', AsyncMock(return_value=True))
    monkeypatch.setattr(menu_mod.MainMenuButtonService, 'get_buttons_for_user', custom_buttons)
    monkeypatch.setattr(type(settings), 'is_text_main_menu_mode', lambda self: text_mode)
    monkeypatch.setattr(type(settings), 'is_admin', lambda self, telegram_id: False)
    monkeypatch.setattr(menu_mod.SupportSettingsService, 'is_moderator', staticmethod(lambda telegram_id: False))

    active = _sub(SubscriptionStatus.ACTIVE.value, 10)
    user = _user([_sub(SubscriptionStatus.EXPIRED.value, -3), active])

    await start_mod._main_menu_keyboard(user, object())

    kwargs = keyboard_builder.await_args.kwargs
    assert kwargs['has_saved_cart'] is True, 'после /start есть «Продолжить оформление»'
    assert kwargs['has_active_subscription'] is True, 'активная подписка не первая — всё равно активна'
    assert kwargs['subscription'] is active
    if text_mode:
        custom_buttons.assert_not_awaited()
        assert kwargs['custom_buttons'] == []
    else:
        assert kwargs['custom_buttons'] == ['CUSTOM']
