"""Общая отправка вложений тикета и кнопка «🗑 Удалить» под ними (пользователь и админ)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramAPIError

from app.utils.ticket_media import delete_ticket_media_notice, send_ticket_media


def _bot():
    return SimpleNamespace(
        send_media_group=AsyncMock(side_effect=lambda **kw: [SimpleNamespace(message_id=100 + len(kw['media']))]),
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=7)),
        send_photo=AsyncMock(return_value=SimpleNamespace(message_id=8)),
        delete_message=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_albums_by_ten_documents_one_by_one():
    bot = _bot()
    items = [{'type': 'photo', 'file_id': f'p{i}'} for i in range(12)] + [{'type': 'document', 'file_id': 'd'}]
    last = await send_ticket_media(bot, 42, items, log_context='test')

    sizes = [len(call.kwargs['media']) for call in bot.send_media_group.await_args_list]
    assert sizes == [10, 2]
    bot.send_document.assert_awaited_once_with(chat_id=42, document='d')
    assert last.message_id == 7


@pytest.mark.asyncio
async def test_failed_chunk_does_not_stop_the_rest():
    bot = _bot()
    bot.send_photo = AsyncMock(side_effect=RuntimeError('boom'))
    items = [{'type': 'photo', 'file_id': 'p'}, {'type': 'document', 'file_id': 'd'}]
    last = await send_ticket_media(bot, 42, items, log_context='test')
    assert last.message_id == 7


@pytest.mark.asyncio
async def test_nothing_sent_returns_none():
    assert await send_ticket_media(_bot(), 42, [], log_context='test') is None


def _callback(data):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
        message=SimpleNamespace(bot=_bot(), delete=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_delete_notice_removes_media_and_itself():
    callback = _callback('admin_delete_message_77')
    await delete_ticket_media_notice(callback, 'admin_delete_message_')
    callback.message.bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)
    callback.message.delete.assert_awaited_once()
    callback.answer.assert_awaited_once_with('✅')


@pytest.mark.asyncio
async def test_delete_notice_bad_id_and_telegram_error():
    callback = _callback('user_delete_message_x')
    await delete_ticket_media_notice(callback, 'user_delete_message_')
    callback.answer.assert_awaited_once_with('❌')

    callback = _callback('user_delete_message_5')
    callback.message.bot.delete_message = AsyncMock(side_effect=TelegramAPIError(method=None, message='gone'))
    await delete_ticket_media_notice(callback, 'user_delete_message_')
    callback.answer.assert_awaited_once_with('✅')
