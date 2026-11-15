"""Normalize ticket galleries for Telegram, preserving legacy single attachments."""

from itertools import groupby

import structlog


logger = structlog.get_logger(__name__)


def get_ticket_media(message) -> list[dict[str, str]]:
    items = getattr(message, 'media_items', None)
    if not items:
        items = [{'type': getattr(message, 'media_type', None), 'file_id': getattr(message, 'media_file_id', None)}]
    return [
        item
        for item in items
        if isinstance(item, dict) and item.get('type') in {'photo', 'video', 'document'} and item.get('file_id')
    ]


def ticket_media_chunks(items: list[dict[str, str]]):
    # Telegram cannot mix documents with photos/videos in one album. Keep order.
    for is_document, group in groupby(items, key=lambda item: item['type'] == 'document'):
        batch = list(group)
        size = 1 if is_document else 10
        for offset in range(0, len(batch), size):
            yield batch[offset : offset + size]


async def send_ticket_media(bot, chat_id: int, attachments: list[dict[str, str]], *, log_context: str):
    """Отправить вложения тикета пачками (одно — отдельным сообщением).

    Сбой одной пачки не останавливает остальные. Возвращает последнее
    отправленное сообщение или None, если ничего не ушло.
    """
    from aiogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo

    last_group_message = None
    for chunk in ticket_media_chunks(attachments):
        media = [
            {'photo': InputMediaPhoto, 'video': InputMediaVideo, 'document': InputMediaDocument}[m['type']](
                media=m['file_id']
            )
            for m in chunk
        ]
        try:
            if len(media) == 1:
                item = media[0]
                sender = getattr(bot, f'send_{item.type.value}')
                messages = [await sender(chat_id=chat_id, **{item.type: item.media})]
            else:
                messages = await bot.send_media_group(chat_id=chat_id, media=media)
            if messages:
                last_group_message = messages[-1]
        except Exception:
            logger.debug(f'Ignored error in {log_context}', exc_info=True)
    return last_group_message


async def delete_ticket_media_notice(callback, callback_prefix: str) -> None:
    """Кнопка «🗑 Удалить» под отправленными вложениями: убрать последнее вложение и само уведомление."""
    from aiogram.exceptions import TelegramAPIError

    try:
        msg_id = int(callback.data.replace(callback_prefix, ''))
    except ValueError:
        await callback.answer('❌')
        return
    try:
        await callback.message.bot.delete_message(chat_id=callback.from_user.id, message_id=msg_id)
        await callback.message.delete()
    except (TelegramAPIError, AttributeError):
        pass
    await callback.answer('✅')
