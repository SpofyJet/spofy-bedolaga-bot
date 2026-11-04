"""Незаконченный шаг ввода не должен перехватывать следующее сообщение.

Раньше: после диплинка /start renew, после ввода промокода (восстанавливался прежний
шаг) и при смене языка (не работала вовсе) оставалось, например, ожидание темы
обращения — и следующее сообщение человека становилось обращением.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database.models import User
from app.states import PromoCodeStates, RegistrationStates, TicketStates
from tests.fixtures.sqlite_memory import memory_session
from tests.handlers.test_gift_deeplink_activation import _TABLES, _make_message


def _state(user_id: int = 22222) -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id))


async def _in_ticket_title_step(state: FSMContext) -> None:
    await state.set_state(TicketStates.waiting_for_title)
    await state.update_data(ticket_draft='x')


@pytest.mark.asyncio
async def test_subscription_deeplink_drops_leftover_input_step(monkeypatch):
    from app.handlers import start

    async with memory_session(monkeypatch, _TABLES) as db:
        user = User(telegram_id=22222, username='rec', balance_kopeks=0, language='ru')
        db.add(user)
        await db.commit()
        await db.refresh(user)

        state = _state(user.telegram_id)
        await _in_ticket_title_step(state)
        opened = AsyncMock(return_value=True)
        monkeypatch.setattr(start, 'open_subscription_deeplink', opened)
        await start.cmd_start(_make_message('/start renew', user.telegram_id, 'rec'), state, db, db_user=user)

    opened.assert_awaited_once()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_promo_input_does_not_bring_back_previous_input_step():
    from app.handlers import promocode

    state = _state()
    await _in_ticket_title_step(state)
    callback = SimpleNamespace(
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )
    db_user = SimpleNamespace(id=7, language='ru')
    await promocode.show_promocode_menu(callback, db_user=db_user, state=state)
    assert await state.get_state() == PromoCodeStates.waiting_for_code.state

    message = MagicMock()
    message.text = 'SPOFY-1'
    message.from_user = SimpleNamespace(id=22222)
    message.answer = AsyncMock()
    with (
        patch.object(
            promocode,
            'activate_promocode_for_registration',
            AsyncMock(return_value={'success': True, 'description': '7 дней'}),
        ),
        patch('app.utils.promo_rate_limiter.promo_limiter.is_blocked', lambda _id: False),
        patch('app.utils.promo_rate_limiter.promo_limiter.can_activate', lambda _id: True),
        patch('app.utils.promo_rate_limiter.promo_limiter.record_activation', MagicMock()),
    ):
        await promocode.process_promocode(message, db_user=db_user, state=state, db=AsyncMock())

    assert await state.get_state() is None, 'следующее сообщение не должно стать темой обращения'
    assert (await state.get_data()).get('ticket_draft') == 'x', 'данные до промокода сохраняются'


@pytest.mark.asyncio
async def test_language_switch_works_during_input_step_and_drops_it():
    from app.handlers import menu

    state = _state()
    await _in_ticket_title_step(state)
    db_user = SimpleNamespace(id=7, language='ru')
    callback = SimpleNamespace(data='language_select:en', answer=AsyncMock())
    show_menu = AsyncMock()
    with (
        patch.object(type(settings), 'is_language_selection_enabled', lambda self: True),
        patch.object(type(settings), 'get_available_languages', lambda self: ['ru', 'en']),
        patch.object(menu, 'show_main_menu', show_menu),
        patch.object(menu, 'update_user', AsyncMock(return_value=SimpleNamespace(id=7, language='en'))),
    ):
        await menu.process_language_change(callback, db_user=db_user, db=AsyncMock(), state=state)

    show_menu.assert_awaited_once()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_language_handler_accepts_any_state_but_registration_language_step():
    from app.handlers import menu

    dp = Dispatcher()
    menu.register_handlers(dp)
    handler = next(h for h in dp.callback_query.handlers if h.callback is menu.process_language_change)
    event = SimpleNamespace(data='language_select:en')

    async def accepts(raw_state):
        result, _ = await handler.check(event, raw_state=raw_state)
        return result

    assert await accepts(None)
    assert await accepts(TicketStates.waiting_for_title.state)
    # Выбор языка при регистрации ведёт start.process_language_selection.
    assert not await accepts(RegistrationStates.waiting_for_language.state)
