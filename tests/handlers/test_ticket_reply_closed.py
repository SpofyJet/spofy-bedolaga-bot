"""Ответ на закрытое обращение: статус проверяется до того, как просить текст.

Раньше «💬 Ответить» на устаревшей карточке переводило в ввод ответа, человек
набирал текст и только потом видел «Обращение закрыто» с единственной кнопкой
«Закрыть уведомление» — текст пропадал.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.models import Ticket, TicketStatus, User
from app.handlers import tickets
from app.services.support_settings_service import SupportSettingsService


def _callback():
    return SimpleNamespace(
        data='reply_ticket_9',
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock(), delete=AsyncMock()),
        answer=AsyncMock(),
    )


def _state():
    return SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock())


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


@pytest.mark.asyncio
async def test_closed_ticket_offers_new_ticket_instead_of_reply_input(monkeypatch):
    monkeypatch.setattr(SupportSettingsService, 'is_tickets_enabled', classmethod(lambda cls: True))
    ticket = Ticket(id=9, user_id=1, title='Старое', status=TicketStatus.CLOSED.value)
    monkeypatch.setattr(tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    callback, state = _callback(), _state()

    await tickets.reply_to_ticket(callback, state, User(id=1, telegram_id=1, language='ru'), AsyncMock())

    state.set_state.assert_not_awaited()
    text = callback.message.edit_text.await_args.args[0]
    assert 'закрыто' in text and 'создайте новое обращение' in text
    assert _callbacks(callback.message.edit_text.await_args.kwargs['reply_markup']) == [
        'create_ticket',
        'back_to_menu',
    ]


@pytest.mark.asyncio
async def test_reply_blocked_ticket_does_not_ask_for_text(monkeypatch):
    ticket = Ticket(id=9, user_id=1, title='Спам', status=TicketStatus.OPEN.value, user_reply_block_permanent=True)
    monkeypatch.setattr(tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    callback, state = _callback(), _state()

    await tickets.reply_to_ticket(callback, state, User(id=1, telegram_id=1, language='ru'), AsyncMock())

    state.set_state.assert_not_awaited()
    assert _callbacks(callback.message.edit_text.await_args.kwargs['reply_markup']) == ['back_to_menu']


@pytest.mark.asyncio
async def test_open_ticket_still_asks_for_reply(monkeypatch):
    ticket = Ticket(id=9, user_id=1, title='Актуальное', status=TicketStatus.ANSWERED.value)
    monkeypatch.setattr(tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    callback, state = _callback(), _state()

    await tickets.reply_to_ticket(callback, state, User(id=1, telegram_id=1, language='ru'), AsyncMock())

    state.update_data.assert_awaited_once_with(ticket_id=9)
    state.set_state.assert_awaited_once_with(tickets.TicketStates.waiting_for_reply)


@pytest.mark.asyncio
async def test_foreign_ticket_is_not_found(monkeypatch):
    ticket = Ticket(id=9, user_id=2, title='Чужое', status=TicketStatus.OPEN.value)
    monkeypatch.setattr(tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    callback, state = _callback(), _state()

    await tickets.reply_to_ticket(callback, state, User(id=1, telegram_id=1, language='ru'), AsyncMock())

    state.set_state.assert_not_awaited()
    assert callback.answer.await_args.kwargs.get('show_alert') is True
