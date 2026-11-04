"""Пользователь видит «обращение», а не «тикет»: подтверждение создания и карточка — из локалей."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.models import Ticket, TicketMessage, User
from app.handlers import tickets
from app.services.event_emitter import event_emitter
from tests.fixtures.sqlite_memory import memory_session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('language', 'expected'),
    [('ru', ('Обращение создано', 'Номер: <b>#', 'Вложений: 1')), ('en', ('Ticket created', 'Number: <b>#'))],
)
async def test_creation_confirmation_uses_locale(monkeypatch, language, expected):
    monkeypatch.setattr(tickets, '_try_delete_message_later', AsyncMock())
    monkeypatch.setattr(tickets, 'notify_admins_about_new_ticket', AsyncMock())
    monkeypatch.setattr(event_emitter, 'emit', AsyncMock())
    async with memory_session(monkeypatch, [User.__table__, Ticket.__table__, TicketMessage.__table__]) as db:
        owner = User(id=1, telegram_id=1, language=language)
        db.add(owner)
        await db.commit()
        state = SimpleNamespace(
            get_state=AsyncMock(return_value=tickets.TicketStates.waiting_for_message),
            get_data=AsyncMock(return_value={'title': 'Не работает <VPN>'}),
            clear=AsyncMock(),
        )
        message = SimpleNamespace(
            chat=SimpleNamespace(id=1),
            message_id=1,
            text=None,
            caption='Не подключается с утра',
            photo=[SimpleNamespace(file_id='masked_photo')] if language == 'ru' else [],
            video=None,
            media_group_id=None,
            answer=AsyncMock(),
            bot=SimpleNamespace(),
        )

        await tickets.handle_ticket_message_input(message, state, owner, db)

        text = message.answer.await_args.args[0]
        for fragment in expected:
            assert fragment in text
        assert 'Тикет' not in text
        assert 'Не работает &lt;VPN&gt;' in text


@pytest.mark.asyncio
async def test_ticket_card_says_obrashchenie(monkeypatch):
    now = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    ticket = Ticket(
        id=12,
        user_id=1,
        title='Оплата',
        status='answered',
        created_at=now,
        messages=[
            TicketMessage(
                id=1, user_id=1, ticket_id=12, message_text='Не прошла оплата', is_from_admin=False, created_at=now
            ),
            TicketMessage(
                id=2,
                user_id=2,
                ticket_id=12,
                message_text='Проверили, всё зачислено',
                is_from_admin=True,
                has_media=True,
                media_type='photo',
                media_file_id='masked_photo',
                created_at=now,
            ),
        ],
    )
    monkeypatch.setattr(tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=ticket))
    sent = AsyncMock()
    monkeypatch.setattr(tickets, 'safe_edit_or_resend', sent)
    callback = SimpleNamespace(data='view_ticket_12', message=SimpleNamespace(), answer=AsyncMock())

    await tickets.view_ticket(callback, User(id=1, telegram_id=1, language='ru'), AsyncMock())

    text = sent.await_args.args[1]
    assert 'Обращение #12' in text
    assert 'Тикет' not in text
    assert 'Тема: Оплата' in text
    assert '🛠️ Поддержка' in text and '👤 Вы' in text
    assert '📎 Вложение: фото' in text
