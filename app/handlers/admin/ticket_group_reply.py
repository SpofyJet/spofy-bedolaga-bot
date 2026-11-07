"""Ответ на обращение прямо из админ-группы.

Админ отвечает (reply / свайп) на карточку обращения в теме уведомлений, и
этот текст уходит пользователю как ответ поддержки — без захода в админку.
Бот ставит на сообщение админа реакцию 👌, если ответ доставлен.

Сообщения из групп по умолчанию отбрасывает ChatTypeFilterMiddleware; он
пропускает сюда только ответы админов/модераторов на карточки бота в чате
ADMIN_NOTIFICATIONS_CHAT_ID (см. ``is_admin_group_ticket_reply``). Обработка
идёт прямо из middleware, минуя остальные (подписка на канал, баннеры и т.п.
для группы не нужны), поэтому сессию БД открываем сами.
"""

from __future__ import annotations

import re

import structlog
from aiogram import types
from aiogram.exceptions import TelegramBadRequest

from app.config import settings
from app.database.crud.ticket import TicketCRUD, TicketMessageCRUD
from app.database.crud.user import get_user_by_telegram_id
from app.database.database import AsyncSessionLocal
from app.database.models import TicketStatus
from app.services.support_settings_service import SupportSettingsService
from app.utils.ticket_text import TICKET_MESSAGE_MAX_LENGTH


logger = structlog.get_logger(__name__)

# «Обращение #123» — новая карточка; «ID: 123» / «ID тикета: 123» — старые
# карточки, которые уже лежат в группе (первое совпадение — номер тикета).
_TICKET_REF = re.compile(r'Обращение\s*#(\d+)')
_LEGACY_REF = re.compile(r'ID(?: тикета)?:\s*(\d+)')


def _admin_chat_id() -> int | None:
    raw = settings.ADMIN_NOTIFICATIONS_CHAT_ID
    try:
        return int(str(raw).strip()) if raw not in (None, '') else None
    except (TypeError, ValueError):
        return None


def extract_ticket_id(message: types.Message | None) -> int | None:
    if message is None:
        return None
    text = message.text or message.caption or ''
    match = _TICKET_REF.search(text) or _LEGACY_REF.search(text)
    return int(match.group(1)) if match else None


def is_admin_group_ticket_reply(message: types.Message) -> bool:
    """Ответ админа/модератора на карточку обращения в админ-чате."""
    chat_id = _admin_chat_id()
    if chat_id is None or message.chat.id != chat_id:
        return False
    reply = message.reply_to_message
    if reply is None or reply.from_user is None or reply.from_user.id != message.bot.id:
        return False
    if _responder_telegram_id(message) is None:
        return False
    return extract_ticket_id(reply) is not None


# Анонимный админ группы пишет от имени служебного бота GroupAnonymousBot,
# а sender_chat = сама группа. Анонимно писать могут только админы группы.
_GROUP_ANONYMOUS_BOT_ID = 1087968824


def _responder_telegram_id(message: types.Message) -> int | None:
    """Telegram ID админа, от имени которого сохраняем ответ, или None."""
    sender = message.from_user
    if sender is None:
        return None
    if (
        sender.id == _GROUP_ANONYMOUS_BOT_ID
        and message.sender_chat is not None
        and message.sender_chat.id == message.chat.id
    ):
        admin_ids = settings.get_admin_ids()
        return admin_ids[0] if admin_ids else None
    if sender.is_bot:
        return None
    if settings.is_admin(sender.id) or SupportSettingsService.is_moderator(sender.id):
        return sender.id
    return None


async def _react(message: types.Message, emoji: str) -> bool:
    try:
        await message.bot.set_message_reaction(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reaction=[types.ReactionTypeEmoji(emoji=emoji)],
        )
        return True
    except Exception as error:  # реакции могут быть выключены в группе
        logger.debug('Ticket reply reaction failed', error=error)
        return False


async def _say(message: types.Message, text: str) -> None:
    try:
        await message.reply(text)
    except TelegramBadRequest as error:
        logger.warning('Ticket group reply: cannot answer in group', error=error)


async def handle_admin_group_ticket_reply(message: types.Message) -> None:
    from app.handlers.admin.tickets import notify_user_about_ticket_reply

    ticket_id = extract_ticket_id(message.reply_to_message)
    if ticket_id is None:
        return

    reply_text = (message.text or message.caption or '').strip()
    media_type = media_file_id = media_caption = None
    if message.photo:
        media_type, media_file_id, media_caption = 'photo', message.photo[-1].file_id, message.caption
    elif message.video:
        media_type, media_file_id, media_caption = 'video', message.video.file_id, message.caption

    if not reply_text and not media_file_id:
        return
    if len(reply_text) > TICKET_MESSAGE_MAX_LENGTH:
        await _say(
            message, f'Не отправлено: длиннее {TICKET_MESSAGE_MAX_LENGTH} символов. Сократите и ответьте ещё раз.'
        )
        return

    try:
        async with AsyncSessionLocal() as db:
            admin = await get_user_by_telegram_id(db, _responder_telegram_id(message))
            if admin is None:
                await _say(message, 'Не отправлено: сначала откройте бота в личке (/start).')
                return
            ticket = await TicketCRUD.get_ticket_by_id(db, ticket_id, load_messages=False, load_user=True)
            if ticket is None:
                await _say(message, f'Обращение #{ticket_id} не найдено.')
                return
            was_closed = ticket.status == TicketStatus.CLOSED.value

            await TicketMessageCRUD.add_message(
                db,
                ticket_id,
                admin.id,
                reply_text,
                is_from_admin=True,
                media_type=media_type,
                media_file_id=media_file_id,
                media_caption=media_caption,
            )
            await notify_user_about_ticket_reply(message.bot, ticket, reply_text, db)
    except Exception as error:
        logger.error('Ticket group reply failed', ticket_id=ticket_id, error=error)
        await _say(message, '❌ Не отправлено, ошибка на стороне бота. Попробуйте ещё раз.')
        return

    logger.info('Ticket answered from admin group', ticket_id=ticket_id, reopened=was_closed)
    if was_closed:
        await _say(message, f'✅ Отправлено. Обращение #{ticket_id} было закрыто — теперь снова открыто.')
    elif not await _react(message, '👌'):
        await _say(message, '✅ Отправлено')


# --- /tickets в админ-группе: карточки всех обращений, ждущих ответа -----------

_WAITING_LIMIT = 15


def is_admin_group_tickets_command(message: types.Message) -> bool:
    chat_id = _admin_chat_id()
    if chat_id is None or message.chat.id != chat_id:
        return False
    text = (message.text or '').strip().lower()
    command = text.split()[0] if text else ''
    if command.split('@', 1)[0] not in ('/tickets', '/обращения'):
        return False
    return _responder_telegram_id(message) is not None


async def handle_admin_group_tickets_command(message: types.Message) -> None:
    from sqlalchemy import select

    from app.database.crud.user import get_user_by_id
    from app.database.models import Ticket, TicketMessage
    from app.handlers.tickets import build_ticket_card_keyboard, build_ticket_card_text

    waiting = (TicketStatus.OPEN.value, TicketStatus.PENDING.value)
    thread_id = message.message_thread_id if message.is_topic_message else None
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(select(Ticket).where(Ticket.status.in_(waiting)).order_by(Ticket.updated_at.asc()))
            tickets = list(rows.scalars().all())
            if not tickets:
                await _say(message, '👌 Все обращения отвечены')
                return
            shown = tickets[:_WAITING_LIMIT]
            for ticket in shown:
                user = await get_user_by_id(db, ticket.user_id)
                body = (
                    await db.execute(
                        select(TicketMessage.message_text)
                        .where(TicketMessage.ticket_id == ticket.id, TicketMessage.is_from_admin.is_(False))
                        .order_by(TicketMessage.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none() or ''
                text = await build_ticket_card_text(db, ticket, user, body, kind='waiting', in_group=True)
                await message.bot.send_message(
                    chat_id=message.chat.id,
                    message_thread_id=thread_id,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=build_ticket_card_keyboard(ticket, user, role='group'),
                    disable_web_page_preview=True,
                )
            rest = len(tickets) - len(shown)
            summary = f'Ждут ответа: {len(tickets)}.' + (
                f' Показаны первые {len(shown)}, остальные — снова /tickets после ответов.' if rest else ''
            )
            await message.bot.send_message(chat_id=message.chat.id, message_thread_id=thread_id, text=summary)
    except Exception as error:
        logger.error('Admin group /tickets failed', error=error)
        await _say(message, '❌ Не получилось показать обращения. Попробуйте ещё раз.')
