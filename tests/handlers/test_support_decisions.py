"""Кнопки «Да / Нет» под вопросами автоответчика поддержки."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from app.handlers.admin import support_decisions as sd
from app.middlewares.chat_type_filter import ChatTypeFilterMiddleware


ADMIN_CHAT = -1001234567890
ADMIN_ID = 111
STRANGER_ID = 222


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setattr(sd.settings, 'ADMIN_NOTIFICATIONS_CHAT_ID', str(ADMIN_CHAT), raising=False)
    monkeypatch.setattr(
        type(sd.settings), 'is_admin', lambda self, telegram_id=None, email=None: telegram_id == ADMIN_ID
    )
    monkeypatch.setattr(sd, 'DECISIONS_PATH', tmp_path / 'nested' / 'support-decisions.jsonl')


def _callback(data='supd:7:y', *, chat_id=ADMIN_CHAT, sender=ADMIN_ID, text='❓ Вопрос <b>'):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=sender, first_name='Дима') if sender else None,
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), text=text, edit_text=AsyncMock()),
        answer=AsyncMock(),
    )


def _records():
    path = sd.DECISIONS_PATH
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


@pytest.mark.parametrize(
    ('data', 'expected'),
    [
        ('supd:7:y', (7, 'y')),
        ('supd:120:n', (120, 'n')),
        ('supd:7:x', None),
        ('supd:abc:y', None),
        ('supd:7', None),
        ('supd:7:y:extra', None),
        ('admin_close_ticket_7', None),
        ('', None),
        (None, None),
    ],
)
def test_parse_decision(data, expected):
    assert sd.parse_decision(data) == expected


def test_only_admin_chat_buttons_are_recognised():
    assert sd.is_support_decision(_callback())
    assert not sd.is_support_decision(_callback(chat_id=-100999))
    assert not sd.is_support_decision(_callback(data='admin_close_ticket_7'))


def test_not_recognised_without_admin_chat(monkeypatch):
    monkeypatch.setattr(sd.settings, 'ADMIN_NOTIFICATIONS_CHAT_ID', None, raising=False)
    assert not sd.is_support_decision(_callback())


@pytest.mark.asyncio
async def test_admin_yes_is_recorded_and_buttons_removed():
    callback = _callback('supd:7:y')
    await sd.handle_support_decision(callback)

    records = _records()
    assert len(records) == 1
    assert records[0]['ask'] == 7
    assert records[0]['decision'] == 'y'
    assert records[0]['by'] == ADMIN_ID

    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.await_args
    assert args[0].startswith('❓ Вопрос <b>')
    assert '✅ Да — Дима · выполняю' in args[0]
    # вопрос ушёл простым текстом: при правке разметку не включаем и кнопки убираем
    assert kwargs == {'reply_markup': None, 'parse_mode': None}
    callback.answer.assert_awaited_once_with('✅ Да')


@pytest.mark.asyncio
async def test_admin_no_is_recorded():
    callback = _callback('supd:8:n')
    await sd.handle_support_decision(callback)

    assert [(r['ask'], r['decision']) for r in _records()] == [(8, 'n')]
    assert '❌ Нет — Дима' in callback.message.edit_text.await_args.args[0]
    assert 'выполняю' not in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_stranger_cannot_decide():
    callback = _callback(sender=STRANGER_ID)
    await sd.handle_support_decision(callback)

    assert _records() == []
    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs == {'show_alert': True}


@pytest.mark.asyncio
async def test_decision_is_kept_when_message_cannot_be_edited():
    callback = _callback()
    callback.message.edit_text.side_effect = TelegramBadRequest(method=MagicMock(), message='message is not modified')
    await sd.handle_support_decision(callback)

    assert len(_records()) == 1
    callback.answer.assert_awaited_once_with('✅ Да')


@pytest.mark.asyncio
async def test_write_failure_is_reported(monkeypatch, tmp_path):
    blocker = tmp_path / 'file'
    blocker.write_text('x')
    monkeypatch.setattr(sd, 'DECISIONS_PATH', blocker / 'support-decisions.jsonl')
    callback = _callback()
    await sd.handle_support_decision(callback)

    callback.message.edit_text.assert_not_awaited()
    assert callback.answer.await_args.kwargs == {'show_alert': True}


def _group_event(data: str, chat_id: int) -> MagicMock:
    event = MagicMock(spec=CallbackQuery)
    event.data = data
    event.from_user = SimpleNamespace(id=ADMIN_ID, first_name='Дима')
    event.message = MagicMock()
    event.message.chat = MagicMock()
    event.message.chat.id = chat_id
    event.message.chat.type = ChatType.SUPERGROUP
    event.message.text = '❓ Вопрос'
    event.message.edit_text = AsyncMock()
    event.answer = AsyncMock()
    return event


@pytest.mark.asyncio
async def test_middleware_routes_decision_from_admin_chat():
    handler = AsyncMock(return_value='handled')
    event = _group_event('supd:9:y', ADMIN_CHAT)
    await ChatTypeFilterMiddleware()(handler, event, {})

    handler.assert_not_awaited()  # до обычных обработчиков нажатие не идёт
    assert [(r['ask'], r['decision']) for r in _records()] == [(9, 'y')]


@pytest.mark.asyncio
async def test_middleware_drops_decision_from_foreign_group():
    handler = AsyncMock(return_value='handled')
    event = _group_event('supd:9:y', -100555)
    result = await ChatTypeFilterMiddleware()(handler, event, {})

    assert result is None
    handler.assert_not_awaited()
    assert _records() == []
