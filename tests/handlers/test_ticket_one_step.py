from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.database.crud.ticket import TicketCRUD
from app.database.models import Ticket, TicketMessage, User
from app.handlers import tickets
from app.localization.texts import get_texts
from app.services.event_emitter import event_emitter
from tests.fixtures.sqlite_memory import memory_session


TABLES = [User.__table__, Ticket.__table__, TicketMessage.__table__]
QUESTION = 'Как добавить устройство в подписку?'


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(tickets, '_try_delete_message_later', AsyncMock())
    monkeypatch.setattr(tickets, 'notify_admins_about_new_ticket', AsyncMock())
    monkeypatch.setattr(event_emitter, 'emit', AsyncMock())
    tickets._ticket_input_batches.clear()


def _state():
    return SimpleNamespace(
        get_state=AsyncMock(return_value=tickets.TicketStates.waiting_for_message),
        get_data=AsyncMock(return_value={}),
        update_data=AsyncMock(),
        set_state=AsyncMock(),
        clear=AsyncMock(),
    )


def _message(*, text=None, photo=None):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        chat=SimpleNamespace(id=1),
        message_id=1,
        text=text,
        caption=None,
        photo=[SimpleNamespace(file_id=photo)] if photo else [],
        video=None,
        media_group_id=None,
        answer=AsyncMock(),
        bot=SimpleNamespace(edit_message_text=AsyncMock()),
    )


async def _create(monkeypatch, message):
    async with memory_session(monkeypatch, TABLES) as db:
        owner = User(id=1, telegram_id=1, language='ru')
        db.add(owner)
        await db.commit()
        await tickets.handle_ticket_message_input(message, _state(), owner, db)
        db.expire_all()
        ticket = (await db.execute(select(Ticket))).scalars().one()
        stored = (await db.execute(select(TicketMessage))).scalars().all()
        return ticket.title, [item.message_text for item in stored]


@pytest.mark.asyncio
async def test_create_button_asks_for_the_question_at_once(monkeypatch):
    monkeypatch.setattr(TicketCRUD, 'is_user_globally_blocked', AsyncMock(return_value=None))
    monkeypatch.setattr(TicketCRUD, 'user_has_active_ticket', AsyncMock(return_value=False))
    prompt = SimpleNamespace(chat=SimpleNamespace(id=1), message_id=7, edit_text=AsyncMock())
    callback = SimpleNamespace(message=prompt, answer=AsyncMock())
    state = _state()

    await tickets.show_ticket_priority_selection(callback, state, SimpleNamespace(id=1, language='ru'), None)

    expected = get_texts('ru').t('TICKET_MESSAGE_INPUT', '').format(limit=tickets.TICKET_MESSAGE_MAX_LENGTH)
    assert prompt.edit_text.await_args.args[0] == expected
    state.set_state.assert_awaited_once_with(tickets.TicketStates.waiting_for_message)


@pytest.mark.asyncio
async def test_first_message_becomes_the_ticket(monkeypatch, quiet):
    title, stored = await _create(monkeypatch, _message(text=QUESTION))

    assert title == QUESTION
    assert stored == [QUESTION]


@pytest.mark.asyncio
async def test_photo_without_text_still_creates_a_ticket(monkeypatch, quiet):
    title, _ = await _create(monkeypatch, _message(photo='masked_photo'))

    assert title == 'Вложение без текста'


def test_title_is_the_first_line_cut_to_the_limit():
    texts = get_texts('ru')

    assert tickets._ticket_title('\n  Не работает  \nподробности', texts) == 'Не работает'
    long_title = tickets._ticket_title('я' * 200, texts)
    assert len(long_title) == tickets.TICKET_TITLE_LENGTH
    assert long_title.endswith('…')


def test_title_step_is_gone():
    assert not hasattr(tickets.TicketStates, 'waiting_for_title')
    assert not hasattr(tickets, 'handle_ticket_title_input')
