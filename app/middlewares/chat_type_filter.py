"""Middleware to ignore non-private chat messages.

When the bot is added as admin to a group or supergroup (including forums
with topics), it should silently drop all incoming messages and callback
queries from those chats. Only private (DM) interactions are processed.

Исключение — кнопки собственной карточки тикета в групповом админ-чате
(«Закрыть», «Заблокировать», «Разблокировать», «Удалить»): их список —
``app.keyboards.group_callbacks``. FSM-кнопки и меню админки в группе
по-прежнему не обрабатываются.

Ещё исключение — сообщения админов в ADMIN_NOTIFICATIONS_CHAT_ID: ответ (reply)
на карточку обращения уходит пользователю, а /tickets показывает карточки
обращений, ждущих ответа (app/handlers/admin/ticket_group_reply.py).

Not registered on chat_member — channel_member.py needs ChatMemberUpdated
events from groups/channels to track required channel subscriptions.
Not registered on pre_checkout_query — no chat context, always private.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.keyboards.group_callbacks import is_group_safe_callback


logger = structlog.get_logger(__name__)


class ChatTypeFilterMiddleware(BaseMiddleware):
    """Drop messages and callback queries from non-private chats."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        if chat is not None and chat.type != ChatType.PRIVATE:
            if isinstance(event, CallbackQuery) and is_group_safe_callback(event.data):
                return await handler(event, data)
            if isinstance(event, Message):
                # Ответ админа на карточку обращения — обрабатываем здесь же,
                # остальные middleware для группы не нужны.
                from app.handlers.admin.ticket_group_reply import (
                    handle_admin_group_ticket_reply,
                    handle_admin_group_tickets_command,
                    is_admin_group_ticket_reply,
                    is_admin_group_tickets_command,
                )

                if is_admin_group_tickets_command(event):
                    return await handle_admin_group_tickets_command(event)
                if is_admin_group_ticket_reply(event):
                    return await handle_admin_group_ticket_reply(event)
            logger.debug(
                'Dropping non-private chat event',
                chat_id=chat.id,
                chat_type=chat.type,
            )
            return None

        return await handler(event, data)
