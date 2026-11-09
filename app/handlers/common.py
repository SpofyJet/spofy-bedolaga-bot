import structlog
from aiogram import Dispatcher, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.keyboards.inline import get_back_keyboard
from app.localization.texts import get_rules, get_texts


logger = structlog.get_logger(__name__)


async def handle_delete_ban_notification(
    callback: types.CallbackQuery,
):
    """Удаляет уведомление о бане при нажатии на кнопку"""
    try:
        await callback.message.delete()
        await callback.answer('Уведомление удалено')
    except Exception as e:
        logger.warning('Не удалось удалить уведомление', error=e)
        await callback.answer('Не удалось удалить', show_alert=False)


async def handle_webhook_notification_close(
    callback: types.CallbackQuery,
):
    """Удаляет webhook-уведомление при нажатии кнопки Закрыть."""
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning('Не удалось удалить webhook-уведомление', e=e)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


async def handle_noop(callback: types.CallbackQuery, db_user: User):
    try:
        await callback.answer()
    except Exception:
        pass


async def handle_current_page(callback: types.CallbackQuery, db_user: User):
    try:
        await callback.answer()
    except Exception:
        pass


async def handle_cancel(callback: types.CallbackQuery, state: FSMContext, db_user: User):
    texts = get_texts(db_user.language)

    await state.clear()
    await callback.message.edit_text(texts.OPERATION_CANCELLED, reply_markup=get_back_keyboard(db_user.language))
    await callback.answer()


_PENDING_SUPPORT_KEY = 'pending_support_message'
_PENDING_SUPPORT_MAX = 3500


def _unknown_message_keyboard(texts, *, can_send: bool) -> types.InlineKeyboardMarkup:
    from app.config import settings

    rows: list[list[types.InlineKeyboardButton]] = []
    if can_send and settings.is_support_tickets_enabled():
        rows.append(
            [
                types.InlineKeyboardButton(
                    text=texts.t('UNKNOWN_SEND_TO_SUPPORT', '💬 Отправить в поддержку'),
                    callback_data='unknown_to_support',
                )
            ]
        )
    elif (url := settings.get_support_contact_url()) is not None:
        rows.append(
            [types.InlineKeyboardButton(text=texts.t('UNKNOWN_OPEN_SUPPORT', '💬 Написать в поддержку'), url=url)]
        )
    rows.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('BACK_TO_MENU_SHORT', '🏠 Главное меню'), callback_data='back_to_menu'
            )
        ]
    )
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_unknown_message(
    message: types.Message,
    state: FSMContext,
    db_user: User | None = None,
):
    """Человек написал боту текстом или прислал фото вне сценария.

    Раньше отвечали «Не понимаю эту команду» с одной кнопкой «Назад», и вопрос
    пропадал. Теперь предлагаем одной кнопкой отправить это же сообщение в
    поддержку: текст и фото запоминаем до нажатия.
    """
    language = db_user.language if db_user else 'ru'
    texts = get_texts(language)

    text = (message.text or message.caption or '').strip()
    photo_id = message.photo[-1].file_id if message.photo else None
    can_send = db_user is not None and bool(text or photo_id)
    if can_send:
        await state.update_data(**{_PENDING_SUPPORT_KEY: {'text': text[:_PENDING_SUPPORT_MAX], 'photo': photo_id}})

    reply = (
        texts.t(
            'UNKNOWN_MESSAGE_TO_SUPPORT',
            'Бот отвечает только на кнопки, поэтому сообщение пока никто не прочитал.\n\n'
            'Нужна помощь? Отправьте его в поддержку — ответ придёт сюда.',
        )
        if can_send
        else texts.t('UNKNOWN_COMMAND_MESSAGE', 'Бот отвечает только на кнопки. Откройте главное меню.')
    )
    await message.answer(reply, reply_markup=_unknown_message_keyboard(texts, can_send=can_send))


async def handle_unknown_to_support(
    callback: types.CallbackQuery,
    state: FSMContext,
    db_user: User,
    db: AsyncSession,
):
    """Одним нажатием превращает сообщение в обращение (или дописывает в открытое)."""
    from app.database.crud.ticket import TicketCRUD, TicketMessageCRUD
    from app.database.models import Ticket, TicketStatus
    from app.handlers.tickets import notify_admins_about_new_ticket, notify_admins_about_ticket_reply
    from app.utils.timezone import format_local_datetime

    texts = get_texts(db_user.language)
    data = await state.get_data()
    pending = data.get(_PENDING_SUPPORT_KEY) or {}
    text = (pending.get('text') or '').strip()
    photo_id = pending.get('photo')
    if not text and not photo_id:
        await callback.answer(
            texts.t('UNKNOWN_SUPPORT_EXPIRED', 'Сообщение уже отправлено или устарело. Напишите его ещё раз.'),
            show_alert=True,
        )
        return

    blocked_until = await TicketCRUD.is_user_globally_blocked(db, db_user.id)
    if blocked_until:
        await callback.answer(
            texts.t('USER_BLOCKED_UNTIL', 'Вы заблокированы до {time}').format(
                time=format_local_datetime(blocked_until, '%d.%m.%Y %H:%M')
            ),
            show_alert=True,
        )
        return

    from sqlalchemy import select

    active_id = (
        await db.execute(
            select(Ticket.id)
            .where(
                Ticket.user_id == db_user.id,
                Ticket.status.in_([TicketStatus.OPEN.value, TicketStatus.ANSWERED.value, TicketStatus.PENDING.value]),
            )
            .order_by(Ticket.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    media = {'media_type': 'photo', 'media_file_id': photo_id, 'media_caption': text or None} if photo_id else {}
    try:
        if active_id is not None:
            await TicketMessageCRUD.add_message(db, active_id, db_user.id, text, is_from_admin=False, **media)
            ticket = await TicketCRUD.get_ticket_by_id(db, active_id, load_messages=False)
            await notify_admins_about_ticket_reply(
                ticket, text, db, media_file_id=photo_id, media_type='photo' if photo_id else None
            )
            ticket_id = active_id
        else:
            first_line = (text.splitlines()[0] if text else '').strip()
            title = (first_line[:57] + '…') if len(first_line) > 58 else (first_line or 'Фото в поддержку')
            ticket = await TicketCRUD.create_ticket(db, db_user.id, title, text, 'normal', **media)
            await notify_admins_about_new_ticket(ticket, db)
            ticket_id = ticket.id
    except Exception as error:
        logger.error('Unknown message → support failed', error=error)
        await callback.answer(
            texts.t('TICKET_CREATE_ERROR', 'Не получилось отправить. Попробуйте ещё раз через минуту.'),
            show_alert=True,
        )
        return

    await state.update_data(**{_PENDING_SUPPORT_KEY: None})
    done = texts.t(
        'UNKNOWN_SENT_TO_SUPPORT',
        '✅ Отправили в поддержку, обращение #{ticket_id}.\nОтвет придёт в этот чат.',
    ).format(ticket_id=ticket_id)
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('VIEW_TICKET', '👁️ Посмотреть обращение'), callback_data=f'view_ticket_{ticket_id}'
                )
            ],
            [
                types.InlineKeyboardButton(
                    text=texts.t('BACK_TO_MENU_SHORT', '🏠 Главное меню'), callback_data='back_to_menu'
                )
            ],
        ]
    )
    try:
        await callback.message.edit_text(done, reply_markup=keyboard)
    except Exception:
        await callback.message.answer(done, reply_markup=keyboard)
    await callback.answer()


async def show_rules(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    get_texts(db_user.language)

    rules_text = await get_rules(db_user.language)

    await callback.message.edit_text(rules_text, reply_markup=get_back_keyboard(db_user.language))
    await callback.answer()


def register_handlers(dp: Dispatcher):
    # Удаление уведомлений
    dp.callback_query.register(handle_delete_ban_notification, F.data == 'ban_notify:delete')
    dp.callback_query.register(handle_webhook_notification_close, F.data == 'webhook:close')

    dp.callback_query.register(show_rules, F.data == 'menu_rules')

    # No-op utility handlers used in many keyboards
    dp.callback_query.register(handle_noop, F.data == 'noop')
    dp.callback_query.register(handle_current_page, F.data == 'current_page')

    dp.callback_query.register(handle_cancel, F.data.in_(['cancel', 'subscription_cancel']))
    dp.callback_query.register(handle_unknown_to_support, F.data == 'unknown_to_support')

    # Самый последний: ловим любые неизвестные текстовые сообщения
    # Исключаем специальные сервисные события (например, успешные платежи)
    # и сообщения от самого бота (например, фото главного меню)
    dp.message.register(
        handle_unknown_message,
        StateFilter(None),
        F.from_user.is_bot.is_(False),
        F.successful_payment.is_(None),
        F.text.is_not(None),
        ~F.text.startswith('/'),
    )

    # Ловим медиа-сообщения (фото, видео, документы, стикеры и т.д.)
    # без активного состояния — чтобы пользователь знал, что бот не принял медиа
    dp.message.register(
        handle_unknown_message,
        StateFilter(None),
        F.from_user.is_bot.is_(False),
        F.successful_payment.is_(None),
        F.text.is_(None),
    )
