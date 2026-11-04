"""Альбом фото и длинный текст, который Telegram режет на части, доходят в обращение целиком.

Раньше троттлинг молча выкидывал сообщения чаще 0.5 с, а обработчик удалял
«лишние» части в окне 2–6 с: из альбома в поддержку попадало только первое
фото, из длинного текста — только первый кусок.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.database.models import Ticket, TicketMessage, User
from app.handlers import tickets
from app.middlewares.throttling import ThrottlingMiddleware
from app.services.event_emitter import event_emitter
from tests.fixtures.sqlite_memory import memory_session


TABLES = [User.__table__, Ticket.__table__, TicketMessage.__table__]


@pytest.fixture
def quiet_ticket_side_effects(monkeypatch):
    monkeypatch.setattr(tickets, 'TICKET_INPUT_DEBOUNCE_SECONDS', 0.05)
    monkeypatch.setattr(tickets, '_try_delete_message_later', AsyncMock())
    monkeypatch.setattr(tickets, 'notify_admins_about_new_ticket', AsyncMock())
    monkeypatch.setattr(tickets, 'notify_admins_about_ticket_reply', AsyncMock())
    monkeypatch.setattr(event_emitter, 'emit', AsyncMock())
    tickets._ticket_input_batches.clear()


def _state(state_value, data):
    return SimpleNamespace(
        get_state=AsyncMock(return_value=state_value),
        get_data=AsyncMock(return_value=data),
        update_data=AsyncMock(),
        clear=AsyncMock(),
    )


def _message(message_id, *, text=None, caption=None, photo=None, media_group_id=None):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        chat=SimpleNamespace(id=1),
        message_id=message_id,
        text=text,
        caption=caption,
        photo=[SimpleNamespace(file_id=photo)] if photo else [],
        video=None,
        media_group_id=media_group_id,
        answer=AsyncMock(),
        bot=SimpleNamespace(edit_message_text=AsyncMock()),
    )


def _album(count, caption='Не подключается, скрины ниже'):
    return [
        _message(i + 1, caption=caption if i == 0 else None, photo=f'masked_photo_{i}', media_group_id='album-1')
        for i in range(count)
    ]


async def _stored_messages(db):
    db.expire_all()
    return (await db.execute(select(TicketMessage).order_by(TicketMessage.id))).scalars().all()


@pytest.mark.asyncio
async def test_album_creates_one_ticket_with_every_photo(monkeypatch, quiet_ticket_side_effects):
    async with memory_session(monkeypatch, TABLES) as db:
        owner = User(id=1, telegram_id=1, language='ru')
        db.add(owner)
        await db.commit()
        state = _state(tickets.TicketStates.waiting_for_message, {'title': 'Не работает VPN'})

        album = _album(3)
        await asyncio.gather(*(tickets.handle_ticket_message_input(m, state, owner, db) for m in album))

        assert len((await db.execute(select(Ticket))).scalars().all()) == 1
        stored = await _stored_messages(db)
        assert len(stored) == 1
        assert stored[0].message_text == 'Не подключается, скрины ниже'
        assert stored[0].media_file_id == 'masked_photo_0'
        assert [item['file_id'] for item in stored[0].media_items] == [f'masked_photo_{i}' for i in range(3)]
        state.clear.assert_awaited()


@pytest.mark.asyncio
async def test_split_long_text_is_kept_whole(monkeypatch, quiet_ticket_side_effects):
    async with memory_session(monkeypatch, TABLES) as db:
        owner = User(id=1, telegram_id=1, language='ru')
        db.add(owner)
        await db.commit()
        state = _state(tickets.TicketStates.waiting_for_message, {'title': 'Длинное описание'})

        first = 'слово ' * 680  # ~4080 символов: Telegram отрезал бы здесь первую часть
        tail = 'и вот окончание описания проблемы'
        parts = [_message(1, text=first), _message(2, text=tail)]
        await asyncio.gather(*(tickets.handle_ticket_message_input(m, state, owner, db) for m in parts))

        assert len((await db.execute(select(Ticket))).scalars().all()) == 1
        stored = await _stored_messages(db)
        assert all(len(m.message_text) <= tickets.TICKET_MESSAGE_MAX_LENGTH for m in stored)
        joined = ''.join(m.message_text for m in stored)
        assert joined.replace(' ', '').replace('\n', '') == (first.strip() + tail).replace(' ', '')
        assert stored[-1].message_text.endswith(tail)


@pytest.mark.asyncio
async def test_short_text_is_processed_without_waiting(monkeypatch, quiet_ticket_side_effects):
    monkeypatch.setattr(tickets, 'TICKET_INPUT_DEBOUNCE_SECONDS', 60)
    async with memory_session(monkeypatch, TABLES) as db:
        owner = User(id=1, telegram_id=1, language='ru')
        db.add(owner)
        await db.commit()
        state = _state(tickets.TicketStates.waiting_for_message, {'title': 'Короткий вопрос'})

        await asyncio.wait_for(
            tickets.handle_ticket_message_input(_message(1, text='Не открывается приложение'), state, owner, db), 5
        )

        assert len(await _stored_messages(db)) == 1


@pytest.mark.asyncio
async def test_reply_album_lands_in_one_reply(monkeypatch, quiet_ticket_side_effects):
    async with memory_session(monkeypatch, TABLES) as db:
        owner = User(id=1, telegram_id=1, language='ru')
        db.add_all([owner, Ticket(id=7, user_id=1, title='Обращение', status='answered')])
        await db.commit()
        state = _state(tickets.TicketStates.waiting_for_reply, {'ticket_id': 7})

        album = _album(4, caption='Вот ещё скрины')
        await asyncio.gather(*(tickets.handle_ticket_reply(m, state, owner, db) for m in album))

        stored = await _stored_messages(db)
        assert len(stored) == 1
        assert len(stored[0].media_items) == 4
        tickets.notify_admins_about_ticket_reply.assert_awaited_once()
        assert sum(m.answer.await_count for m in album) == 1, 'подтверждение — одно на весь альбом'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('state_value', 'reaches_handler'),
    [
        (tickets.TicketStates.waiting_for_message.state, True),
        (tickets.TicketStates.waiting_for_reply.state, True),
        (None, False),
    ],
)
async def test_throttling_lets_ticket_input_parts_through(monkeypatch, state_value, reaches_handler):
    from aiogram.types import Message

    middleware = ThrottlingMiddleware()
    handler = AsyncMock(return_value='ok')

    def make_event():
        # isinstance(event, Message) в middleware; поля pydantic-модели — не атрибуты класса
        event = MagicMock()
        event.__class__ = Message
        event.from_user.id = 5
        event.text = 'часть'
        event.answer = AsyncMock()
        return event

    data = {'state': SimpleNamespace(get_state=AsyncMock(return_value=state_value))}
    await middleware(handler, make_event(), data)
    second = make_event()
    await middleware(handler, second, data)

    assert handler.await_count == (2 if reaches_handler else 1)
    if not reaches_handler:
        second.answer.assert_awaited()
