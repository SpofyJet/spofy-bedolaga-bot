import asyncio
import contextlib
import html
import time
from dataclasses import dataclass, field

import structlog
from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InaccessibleMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.ticket import TicketCRUD, TicketMessageCRUD
from app.database.crud.user import get_user_by_id
from app.database.models import Ticket, TicketStatus, User
from app.keyboards.inline import (
    get_my_tickets_keyboard,
    get_ticket_cancel_keyboard,
    get_ticket_notification_keyboard,
    get_ticket_reply_cancel_keyboard,
    get_ticket_view_keyboard,
)
from app.localization.texts import get_texts
from app.services.admin_notification_service import AdminNotificationService
from app.utils.background import spawn_background_task
from app.utils.formatters import format_username_link
from app.utils.miniapp_buttons import build_admin_ticket_cabinet_button
from app.utils.photo_message import edit_or_answer_photo, safe_edit_or_resend
from app.utils.ticket_media import get_ticket_media, ticket_media_chunks
from app.utils.ticket_text import (
    TICKET_MESSAGE_MAX_LENGTH,
    TICKET_PAGE_MAX_LEN,
    build_ticket_pages,
    split_long_block,
)
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)


class TicketStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_message = State()
    waiting_for_reply = State()


async def show_ticket_priority_selection(
    callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession
):
    """Начать создание тикета без выбора приоритета: сразу просим заголовок"""
    texts = get_texts(db_user.language)

    # Глобальный блок и наличие активного тикета
    from app.database.crud.ticket import TicketCRUD

    blocked_until = await TicketCRUD.is_user_globally_blocked(db, db_user.id)
    if blocked_until:
        if blocked_until.year > 9999 - 1:
            await callback.answer(
                texts.t('USER_BLOCKED_FOREVER', 'Вы заблокированы для обращений в поддержку.'), show_alert=True
            )
        else:
            await callback.answer(
                texts.t('USER_BLOCKED_UNTIL', 'Вы заблокированы до {time}').format(
                    time=format_local_datetime(blocked_until, '%d.%m.%Y %H:%M')
                ),
                show_alert=True,
            )
        return
    if await TicketCRUD.user_has_active_ticket(db, db_user.id):
        await callback.answer(
            texts.t('TICKET_ALREADY_OPEN', 'У вас уже есть незакрытое обращение. Сначала закройте его.'),
            show_alert=True,
        )
        return

    prompt_text = texts.t('TICKET_TITLE_INPUT', 'Введите тему обращения:')
    cancel_kb = get_ticket_cancel_keyboard(db_user.language)
    prompt_msg = callback.message
    try:
        await callback.message.edit_text(prompt_text, reply_markup=cancel_kb)
    except TelegramBadRequest:
        # Предыдущее сообщение — фото (нет текста для edit_text), удаляем и шлём новое
        try:
            await callback.message.delete()
        except (TelegramAPIError, AttributeError):
            pass
        prompt_msg = await callback.message.answer(prompt_text, reply_markup=cancel_kb)
    # Запоминаем исходное сообщение бота, чтобы далее редактировать его, а не слать новые
    await state.update_data(prompt_chat_id=prompt_msg.chat.id, prompt_message_id=prompt_msg.message_id)
    await state.set_state(TicketStates.waiting_for_title)
    await callback.answer()


async def handle_ticket_title_input(message: types.Message, state: FSMContext, db_user: User, db: AsyncSession):
    # Проверяем, что пользователь в правильном состоянии
    current_state = await state.get_state()
    if current_state != TicketStates.waiting_for_title:
        return

    """Обработать ввод заголовка тикета"""
    if not message.text:
        spawn_background_task(_try_delete_message_later(message.bot, message.chat.id, message.message_id, 2.0))
        return
    title = message.text.strip()

    data_prompt = await state.get_data()
    prompt_chat_id = data_prompt.get('prompt_chat_id')
    prompt_message_id = data_prompt.get('prompt_message_id')
    # Удалим сообщение пользователя через 2 секунды, чтобы не засорять чат
    spawn_background_task(_try_delete_message_later(message.bot, message.chat.id, message.message_id, 2.0))
    if len(title) < 5:
        texts = get_texts(db_user.language)
        text_val = texts.t(
            'TICKET_TITLE_TOO_SHORT', 'Заголовок должен содержать минимум 5 символов. Попробуйте еще раз:'
        )
        await _edit_or_send(message, prompt_chat_id, prompt_message_id, text_val, db_user.language)
        return

    if len(title) > 255:
        texts = get_texts(db_user.language)
        text_val = texts.t(
            'TICKET_TITLE_TOO_LONG', 'Заголовок слишком длинный. Максимум 255 символов. Попробуйте еще раз:'
        )
        await _edit_or_send(message, prompt_chat_id, prompt_message_id, text_val, db_user.language)
        return

    # Глобальный блок
    from app.database.crud.ticket import TicketCRUD

    blocked_until = await TicketCRUD.is_user_globally_blocked(db, db_user.id)
    if blocked_until:
        texts = get_texts(db_user.language)
        if blocked_until.year > 9999 - 1:
            await message.answer(texts.t('USER_BLOCKED_FOREVER', 'Вы заблокированы для обращений в поддержку.'))
        else:
            await message.answer(
                texts.t('USER_BLOCKED_UNTIL', 'Вы заблокированы до {time}').format(
                    time=format_local_datetime(blocked_until, '%d.%m.%Y %H:%M')
                )
            )
        await state.clear()
        return

    await state.update_data(title=title)

    texts = get_texts(db_user.language)
    text_val = texts.t(
        'TICKET_MESSAGE_INPUT', 'Опишите проблему (до {limit} символов) или отправьте фото с подписью:'
    ).format(limit=TICKET_MESSAGE_MAX_LENGTH)
    await _edit_or_send(message, prompt_chat_id, prompt_message_id, text_val, db_user.language)

    await state.set_state(TicketStates.waiting_for_message)


# Пачки сообщений в состояниях ввода обращения/ответа. Альбом из нескольких фото приходит отдельными апдейтами
# с общим media_group_id, а длинный текст Telegram сам режет на части по ~4096 символов. Первая часть ждёт
# короткую паузу, остальные складываются в ту же пачку, и обращение создаётся (или ответ добавляется) один раз
# со всеми частями.
TICKET_INPUT_DEBOUNCE_SECONDS = 1.0
TICKET_INPUT_MAX_WAIT_SECONDS = 6.0
# Первая часть разрезанного Telegram текста почти всегда длиннее этого порога;
# короткое сообщение обрабатываем сразу, без паузы.
TICKET_SPLIT_TEXT_MIN_LENGTH = 3000
# Склеенный текст хранится несколькими сообщениями обращения по
# TICKET_MESSAGE_MAX_LENGTH; общий потолок защищает от простыней.
TICKET_INPUT_MAX_LENGTH = TICKET_MESSAGE_MAX_LENGTH * 4


class _TicketInputBatch:
    def __init__(self, first: types.Message):
        now = time.monotonic()
        self.messages: list[types.Message] = [first]
        self.started_at = now
        self.last_at = now
        self._taken = 0

    def add(self, message: types.Message) -> None:
        self.messages.append(message)
        self.last_at = time.monotonic()

    def take(self) -> list[types.Message]:
        """Части, которые ещё не обработаны, в порядке отправки."""
        fresh = self.messages[self._taken :]
        self._taken = len(self.messages)
        return sorted(fresh, key=lambda m: m.message_id)


_ticket_input_batches: dict[tuple[str, int], _TicketInputBatch] = {}


def _may_have_more_parts(message: types.Message) -> bool:
    if getattr(message, 'media_group_id', None):
        return True
    return len(message.text or '') >= TICKET_SPLIT_TEXT_MIN_LENGTH


@contextlib.asynccontextmanager
async def _ticket_input_batch(kind: str, user_id: int, message: types.Message):
    """Отдаёт пачку первому сообщению и None — остальным частям той же пачки.

    Части, пришедшие пока первая ещё обрабатывается, тоже попадают в пачку:
    их забирает `batch.take()` после создания обращения.
    """
    key = (kind, user_id)
    batch = _ticket_input_batches.get(key)
    if batch is not None:
        batch.add(message)
        yield None
        return

    batch = _TicketInputBatch(message)
    _ticket_input_batches[key] = batch
    try:
        if _may_have_more_parts(message):
            while True:
                deadline = min(
                    batch.last_at + TICKET_INPUT_DEBOUNCE_SECONDS,
                    batch.started_at + TICKET_INPUT_MAX_WAIT_SECONDS,
                )
                delay = deadline - time.monotonic()
                if delay <= 0:
                    break
                await asyncio.sleep(delay)
        yield batch
    finally:
        if _ticket_input_batches.get(key) is batch:
            del _ticket_input_batches[key]


@dataclass
class _TicketInputContent:
    text: str
    media_items: list[dict[str, str]] = field(default_factory=list)
    caption: str | None = None


def _ticket_input_content(messages: list[types.Message]) -> _TicketInputContent:
    texts: list[str] = []
    content = _TicketInputContent(text='')
    for item in messages:
        part_text = (item.text or item.caption or '').strip()
        if part_text:
            texts.append(part_text)
        # Сохраняем вложение отдельно от подписи, в том числе видео без текста.
        if item.photo:
            content.media_items.append({'type': 'photo', 'file_id': item.photo[-1].file_id})
        elif item.video:
            content.media_items.append({'type': 'video', 'file_id': item.video.file_id})
        else:
            continue
        if content.caption is None:
            content.caption = item.caption
    content.text = '\n'.join(texts)
    return content


def _ticket_media_fields(content: _TicketInputContent) -> dict:
    """Поля вложений для TicketMessage: первое вложение — основное, весь альбом — в media_items."""
    if not content.media_items:
        return {}
    first = content.media_items[0]
    fields = {'media_type': first['type'], 'media_file_id': first['file_id'], 'media_caption': content.caption}
    if len(content.media_items) > 1:
        fields['media_items'] = list(content.media_items)
    return fields


def _ticket_text_chunks(text: str, limit: int) -> list[str]:
    """Режет текст на сообщения обращения по limit символов, ничего не теряя."""
    if len(text) <= limit:
        return [text]
    return split_long_block(text, limit)


async def _append_ticket_messages(db: AsyncSession, ticket_id: int, user_id: int, content: _TicketInputContent) -> bool:
    """Добавляет части пользователя в обращение: вложения — к первому сообщению."""
    if not content.text and not content.media_items:
        return False
    media_fields = _ticket_media_fields(content)
    for chunk in _ticket_text_chunks(content.text, TICKET_MESSAGE_MAX_LENGTH):
        await TicketMessageCRUD.add_message(db, ticket_id, user_id, chunk, is_from_admin=False, **media_fields)
        media_fields = {}
    return True


def _schedule_user_message_delete(message: types.Message) -> None:
    # Удалим сообщение пользователя через 2 секунды, чтобы не засорять чат
    try:
        spawn_background_task(_try_delete_message_later(message.bot, message.chat.id, message.message_id, 2.0))
    except Exception as exc:
        logger.debug('Сообщение обращения не поставлено на удаление', error=str(exc))


async def handle_ticket_message_input(message: types.Message, state: FSMContext, db_user: User, db: AsyncSession):
    # Проверяем, что пользователь в правильном состоянии
    current_state = await state.get_state()
    if current_state != TicketStates.waiting_for_message:
        return

    async with _ticket_input_batch('create', db_user.id, message) as batch:
        if batch is None:
            # Часть альбома или длинного текста — её заберёт первое сообщение пачки.
            _schedule_user_message_delete(message)
            return
        await _create_ticket_from_batch(batch, state, db_user, db)


async def _create_ticket_from_batch(batch: _TicketInputBatch, state: FSMContext, db_user: User, db: AsyncSession):
    """Обработать ввод сообщения тикета и создать тикет"""
    messages = batch.take()
    message = messages[0]
    texts = get_texts(db_user.language)
    data_prompt = await state.get_data()
    prompt_chat_id = data_prompt.get('prompt_chat_id')
    prompt_message_id = data_prompt.get('prompt_message_id')

    # Глобальный блок
    blocked_until = await TicketCRUD.is_user_globally_blocked(db, db_user.id)
    if blocked_until:
        text_msg = (
            texts.t('USER_BLOCKED_FOREVER', 'Вы заблокированы для обращений в поддержку.')
            if blocked_until.year > 9999 - 1
            else texts.t('USER_BLOCKED_UNTIL', 'Вы заблокированы до {time}').format(
                time=format_local_datetime(blocked_until, '%d.%m.%Y %H:%M')
            )
        )
        if prompt_chat_id and prompt_message_id:
            try:
                await message.bot.edit_message_text(chat_id=prompt_chat_id, message_id=prompt_message_id, text=text_msg)
            except TelegramBadRequest:
                await message.answer(text_msg)
        else:
            await message.answer(text_msg)
        await state.clear()
        return

    for item in messages:
        _schedule_user_message_delete(item)

    content = _ticket_input_content(messages)
    message_text = content.text
    # Вложение может описывать проблему без текстовой подписи.
    if len(message_text) < 10 and not content.media_items:
        err_text = texts.t(
            'TICKET_MESSAGE_TOO_SHORT', 'Сообщение слишком короткое. Опишите проблему подробнее или отправьте фото:'
        )
        await _edit_or_send(message, prompt_chat_id, prompt_message_id, err_text, db_user.language)
        return

    # Длинный текст (Telegram режет его на части) сохраняем целиком несколькими
    # сообщениями обращения; ничего не отбрасываем втихую.
    if len(message_text) > TICKET_INPUT_MAX_LENGTH:
        err_text = texts.t(
            'TICKET_MESSAGE_TOO_LONG',
            'Сообщение слишком длинное. Максимум {limit} символов. Сократите текст и отправьте еще раз:',
        ).format(limit=TICKET_INPUT_MAX_LENGTH)
        await _edit_or_send(message, prompt_chat_id, prompt_message_id, err_text, db_user.language)
        return
    chunks = _ticket_text_chunks(message_text, TICKET_MESSAGE_MAX_LENGTH)

    title = data_prompt.get('title')
    priority = 'normal'

    try:
        ticket = await TicketCRUD.create_ticket(
            db,
            db_user.id,
            title,
            chunks[0],
            priority,
            **_ticket_media_fields(content),
        )
        for chunk in chunks[1:]:
            await TicketMessageCRUD.add_message(db, ticket.id, db_user.id, chunk, is_from_admin=False)
        # Части, пришедшие пока обращение создавалось, — туда же
        await _append_ticket_messages(db, ticket.id, db_user.id, _ticket_input_content(batch.take()))
        await state.clear()
        await _append_ticket_messages(db, ticket.id, db_user.id, _ticket_input_content(batch.take()))

        # Ограничим длину подтверждения чтобы не упереться в лимиты
        safe_title = html.escape(title if len(title) <= 200 else (title[:197] + '...'))
        creation_text = (
            texts.t('TICKET_CREATED_SUCCESS', '✅ Обращение создано!')
            + '\n\n'
            + texts.t('TICKET_CREATED_DETAILS', 'Номер: <b>#{ticket_id}</b>\nТема: {title}').format(
                ticket_id=ticket.id, title=safe_title
            )
        )
        if content.media_items:
            creation_text += '\n' + texts.t('TICKET_CREATED_ATTACHMENTS', 'Вложений: {count}').format(
                count=len(content.media_items)
            )

        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t('VIEW_TICKET', '👁️ Посмотреть обращение'),
                        callback_data=f'view_ticket_{ticket.id}',
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text=texts.t('BACK_TO_MENU', '🏠 В главное меню'), callback_data='back_to_menu'
                    )
                ],
            ]
        )
        if prompt_chat_id and prompt_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=prompt_chat_id,
                    message_id=prompt_message_id,
                    text=creation_text,
                    reply_markup=keyboard,
                    parse_mode='HTML',
                )
            except TelegramBadRequest:
                await message.answer(creation_text, reply_markup=keyboard, parse_mode='HTML')
        else:
            await message.answer(creation_text, reply_markup=keyboard, parse_mode='HTML')

        # Уведомить админов
        await notify_admins_about_new_ticket(ticket, db)

    except Exception as e:
        logger.error('Error creating ticket', error=e)
        texts = get_texts(db_user.language)
        await message.answer(texts.t('TICKET_CREATE_ERROR', '❌ Не удалось создать обращение. Попробуйте позже.'))


async def show_my_tickets(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    # Определяем текущую страницу
    current_page = 1
    if callback.data.startswith('my_tickets_page_'):
        try:
            current_page = int(callback.data.replace('my_tickets_page_', ''))
        except ValueError:
            current_page = 1

    # Пагинация открытых тикетов из БД
    per_page = 10
    total_open = await TicketCRUD.count_user_tickets_by_statuses(
        db, db_user.id, [TicketStatus.OPEN.value, TicketStatus.ANSWERED.value, TicketStatus.PENDING.value]
    )
    total_pages = max(1, (total_open + per_page - 1) // per_page)
    current_page = max(1, min(current_page, total_pages))
    offset = (current_page - 1) * per_page
    open_tickets = await TicketCRUD.get_user_tickets_by_statuses(
        db,
        db_user.id,
        [TicketStatus.OPEN.value, TicketStatus.ANSWERED.value, TicketStatus.PENDING.value],
        limit=per_page,
        offset=offset,
    )

    # Проверка на отсутствие тикетов совсем (ни открытых, ни закрытых)
    has_closed_any = await TicketCRUD.count_user_tickets_by_statuses(db, db_user.id, [TicketStatus.CLOSED.value]) > 0
    if not open_tickets and not has_closed_any:
        await callback.message.edit_text(
            texts.t('NO_TICKETS', 'У вас пока нет обращений.'),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('CREATE_TICKET_BUTTON', '🎫 Создать обращение'), callback_data='create_ticket'
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('VIEW_CLOSED_TICKETS', '🟢 Закрытые обращения'),
                            callback_data='my_tickets_closed',
                        )
                    ],
                    [types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_support')],
                ]
            ),
        )
        await callback.answer()
        return

    # Открытые с пагинацией (DB)
    open_data = [{'id': t.id, 'title': t.title, 'status_emoji': t.status_emoji} for t in open_tickets]
    keyboard = get_my_tickets_keyboard(
        open_data,
        current_page=current_page,
        total_pages=total_pages,
        language=db_user.language,
        page_prefix='my_tickets_page_',
    )
    # Добавим кнопку перехода к закрытым
    keyboard.inline_keyboard.insert(
        0,
        [
            types.InlineKeyboardButton(
                text=texts.t('VIEW_CLOSED_TICKETS', '🟢 Закрытые обращения'), callback_data='my_tickets_closed'
            )
        ],
    )
    # Всегда используем фото-рендер с логотипом (утилита сама сделает фоллбек при необходимости)
    await edit_or_answer_photo(
        callback=callback,
        caption=texts.t('MY_TICKETS_TITLE', '📋 Ваши обращения:'),
        keyboard=keyboard,
        parse_mode='HTML',
    )
    await callback.answer()


async def show_my_tickets_closed(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    # Пагинация закрытых
    current_page = 1
    data_str = callback.data
    if data_str.startswith('my_tickets_closed_page_'):
        try:
            current_page = int(data_str.replace('my_tickets_closed_page_', ''))
        except ValueError:
            current_page = 1

    per_page = 10
    total_closed = await TicketCRUD.count_user_tickets_by_statuses(db, db_user.id, [TicketStatus.CLOSED.value])
    if total_closed == 0:
        await callback.message.edit_text(
            texts.t('NO_CLOSED_TICKETS', 'Закрытых обращений пока нет.'),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('BACK_TO_OPEN_TICKETS', '🔴 Открытые обращения'), callback_data='my_tickets'
                        )
                    ],
                    [types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_support')],
                ]
            ),
        )
        await callback.answer()
        return
    total_pages = max(1, (total_closed + per_page - 1) // per_page)
    current_page = max(1, min(current_page, total_pages))
    offset = (current_page - 1) * per_page
    tickets = await TicketCRUD.get_user_tickets_by_statuses(
        db, db_user.id, [TicketStatus.CLOSED.value], limit=per_page, offset=offset
    )
    data = [{'id': t.id, 'title': t.title, 'status_emoji': t.status_emoji} for t in tickets]
    kb = get_my_tickets_keyboard(
        data,
        current_page=current_page,
        total_pages=total_pages,
        language=db_user.language,
        page_prefix='my_tickets_closed_page_',
    )
    kb.inline_keyboard.insert(
        0,
        [
            types.InlineKeyboardButton(
                text=texts.t('BACK_TO_OPEN_TICKETS', '🔴 Открытые обращения'), callback_data='my_tickets'
            )
        ],
    )
    await edit_or_answer_photo(
        callback=callback,
        caption=texts.t('CLOSED_TICKETS_TITLE', '🟢 Закрытые обращения:'),
        keyboard=kb,
        parse_mode='HTML',
    )
    await callback.answer()


async def view_ticket(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Показать детали тикета с пагинацией"""
    data_str = callback.data
    # None — страница не задана: открываем последнюю, где лежат свежие сообщения
    page = None
    ticket_id = None
    if data_str.startswith('ticket_view_page_'):
        # format: ticket_view_page_{ticket_id}_{page}
        try:
            _, _, _, tid, p = data_str.split('_')
            ticket_id = int(tid)
            page = max(1, int(p))
        except Exception:
            logger.debug('Ignored error in view_ticket', exc_info=True)
    if ticket_id is None:
        ticket_id = int(data_str.replace('view_ticket_', ''))

    ticket = await TicketCRUD.get_ticket_by_id(db, ticket_id, load_messages=True)

    if not ticket or ticket.user_id != db_user.id:
        texts = get_texts(db_user.language)
        await callback.answer(texts.t('TICKET_NOT_FOUND', 'Обращение не найдено.'), show_alert=True)
        return

    texts = get_texts(db_user.language)

    # Формируем текст тикета
    status_text = {
        TicketStatus.OPEN.value: texts.t('TICKET_STATUS_OPEN', 'Открыт'),
        TicketStatus.ANSWERED.value: texts.t('TICKET_STATUS_ANSWERED', 'Отвечен'),
        TicketStatus.CLOSED.value: texts.t('TICKET_STATUS_CLOSED', 'Закрыт'),
        TicketStatus.PENDING.value: texts.t('TICKET_STATUS_PENDING', 'В ожидании'),
    }.get(ticket.status, ticket.status)

    header = (
        texts.t('TICKET_CARD_HEADER', '🎫 <b>Обращение #{ticket_id}</b>').format(ticket_id=ticket.id)
        + '\n\n'
        + texts.t('TICKET_CARD_DETAILS', 'Тема: {title}\nСтатус: {status}\nСоздано: {created_at}').format(
            title=html.escape(ticket.title or ''),
            status=f'{ticket.status_emoji} {status_text}',
            created_at=format_local_datetime(ticket.created_at, '%d.%m.%Y %H:%M'),
        )
        + '\n\n'
    )
    sender_user = texts.t('TICKET_CARD_SENDER_USER', '👤 Вы')
    sender_support = texts.t('TICKET_CARD_SENDER_SUPPORT', '🛠️ Поддержка')
    attachment_kinds = {
        'photo': texts.t('TICKET_ATTACHMENT_KIND_PHOTO', 'фото'),
        'video': texts.t('TICKET_ATTACHMENT_KIND_VIDEO', 'видео'),
        'document': texts.t('TICKET_ATTACHMENT_KIND_DOCUMENT', 'файл'),
    }
    message_blocks: list[str] = []
    if ticket.messages:
        message_blocks.append(
            texts.t('TICKET_CARD_MESSAGES', '💬 Сообщения ({count}):').format(count=len(ticket.messages)) + '\n\n'
        )
        for msg in ticket.messages:
            sender = sender_user if msg.is_user_message else sender_support
            block = f'{sender} ({format_local_datetime(msg.created_at, "%d.%m %H:%M")}):\n{html.escape(msg.message_text or "")}\n\n'
            for item in get_ticket_media(msg):
                block += (
                    texts.t('TICKET_CARD_ATTACHMENT', '📎 Вложение: {kind}').format(kind=attachment_kinds[item['type']])
                    + '\n\n'
                )
            message_blocks.append(block)
    pages = build_ticket_pages(header, message_blocks, max_len=TICKET_PAGE_MAX_LEN)
    total_pages = len(pages)
    page = total_pages if page is None else min(page, total_pages)

    keyboard = get_ticket_view_keyboard(
        ticket_id,
        ticket.is_closed,
        db_user.language,
    )
    # Если есть фото или видео — добавим кнопку для просмотра
    has_attachments = any(get_ticket_media(m) for m in ticket.messages or [])
    if has_attachments:
        try:
            # n6-П14: служебные ряды — после действий тикета, перед «Назад»
            keyboard.inline_keyboard.insert(
                max(0, len(keyboard.inline_keyboard) - 1),
                [
                    types.InlineKeyboardButton(
                        text=texts.t('TICKET_ATTACHMENTS', '📎 Вложения'),
                        callback_data=f'ticket_attachments_{ticket_id}',
                    )
                ],
            )
        except Exception:
            logger.debug('Ignored error in view_ticket', exc_info=True)
    # Пагинация
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(
                types.InlineKeyboardButton(text='⬅️', callback_data=f'ticket_view_page_{ticket_id}_{page - 1}')
            )
        nav_row.append(types.InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
        if page < total_pages:
            nav_row.append(
                types.InlineKeyboardButton(text='➡️', callback_data=f'ticket_view_page_{ticket_id}_{page + 1}')
            )
        if getattr(keyboard, 'inline_keyboard', None) is not None:
            # Пагинация — после действий, прямо над «Назад»
            keyboard.inline_keyboard.insert(max(0, len(keyboard.inline_keyboard) - 1), nav_row)
    # Показываем как текст (чтобы не упереться в caption лимит)
    page_text = pages[page - 1]
    await safe_edit_or_resend(callback.message, page_text, keyboard)
    await callback.answer()


async def send_ticket_attachments(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    try:
        await callback.answer(texts.t('SENDING_ATTACHMENTS', '📎 Отправляю вложения...'))
    except TelegramAPIError:
        pass
    try:
        ticket_id = int(callback.data.replace('ticket_attachments_', ''))
    except ValueError:
        await callback.answer(texts.t('TICKET_NOT_FOUND', 'Обращение не найдено.'), show_alert=True)
        return

    ticket = await TicketCRUD.get_ticket_by_id(db, ticket_id, load_messages=True)
    if not ticket or ticket.user_id != db_user.id:
        await callback.answer(texts.t('TICKET_NOT_FOUND', 'Обращение не найдено.'), show_alert=True)
        return

    attachments = [item for message in ticket.messages for item in get_ticket_media(message)]
    if not attachments:
        await callback.answer(texts.t('NO_ATTACHMENTS', 'Вложений нет.'), show_alert=True)
        return

    # Telegram ограничивает media group до 10 элементов. Отправим чанками.
    from aiogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo

    chunks = ticket_media_chunks(attachments)
    last_group_message = None
    for chunk in chunks:
        media = [
            {'photo': InputMediaPhoto, 'video': InputMediaVideo, 'document': InputMediaDocument}[m['type']](
                media=m['file_id']
            )
            for m in chunk
        ]
        try:
            if len(media) == 1:
                item = media[0]
                sender = getattr(callback.message.bot, f'send_{item.type.value}')
                messages = [await sender(chat_id=callback.from_user.id, **{item.type: item.media})]
            else:
                messages = await callback.message.bot.send_media_group(chat_id=callback.from_user.id, media=media)
            if messages:
                last_group_message = messages[-1]
        except Exception:
            logger.debug('Ignored error in send_ticket_attachments', exc_info=True)
    if last_group_message:
        try:
            kb = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('DELETE_MESSAGE', '🗑 Удалить'),
                            callback_data=f'user_delete_message_{last_group_message.message_id}',
                        )
                    ]
                ]
            )
            await callback.message.bot.send_message(
                chat_id=callback.from_user.id, text=texts.t('ATTACHMENTS_SENT', 'Вложения отправлены.'), reply_markup=kb
            )
        except (TelegramAPIError, AttributeError):
            pass
    else:
        try:
            await callback.answer(texts.t('ATTACHMENTS_SENT', 'Вложения отправлены.'))
        except TelegramAPIError:
            pass


async def user_delete_message(callback: types.CallbackQuery):
    try:
        msg_id = int(callback.data.replace('user_delete_message_', ''))
    except ValueError:
        await callback.answer('❌')
        return
    try:
        await callback.message.bot.delete_message(chat_id=callback.from_user.id, message_id=msg_id)
        await callback.message.delete()
    except (TelegramAPIError, AttributeError):
        pass
    await callback.answer('✅')


async def _edit_or_send(
    message: types.Message,
    chat_id: int | None,
    message_id: int | None,
    text: str,
    language: str,
) -> None:
    """Попытаться отредактировать prompt-сообщение, при неудаче — отправить новое."""
    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=get_ticket_cancel_keyboard(language),
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=get_ticket_cancel_keyboard(language))


async def _try_delete_message_later(bot: Bot, chat_id: int, message_id: int, delay_seconds: float = 1.0):
    try:
        await asyncio.sleep(delay_seconds)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        # В приватных чатах удаление сообщений пользователя может быть недоступно — игнорируем ошибки
        logger.debug('Ignored error in _try_delete_message_later', exc_info=True)


def _ticket_reply_unavailable_view(texts, ticket: Ticket) -> tuple[str, types.InlineKeyboardMarkup]:
    """Экран «ответить нельзя»: для закрытого обращения — создать новое или в меню."""
    rows: list[list[types.InlineKeyboardButton]] = []
    if ticket.status == TicketStatus.CLOSED.value:
        text = texts.t('TICKET_CLOSED_NO_REPLY', '❌ Обращение закрыто, ответить невозможно.')
        try:
            from app.services.support_settings_service import SupportSettingsService

            tickets_enabled = SupportSettingsService.is_tickets_enabled()
        except Exception:
            tickets_enabled = True
        if tickets_enabled:
            text += '\n\n' + texts.t('TICKET_CLOSED_CREATE_NEW_HINT', 'Если вопрос остался — создайте новое обращение.')
            rows.append(
                [
                    types.InlineKeyboardButton(
                        text=texts.t('CREATE_TICKET_BUTTON', '🎫 Создать обращение'), callback_data='create_ticket'
                    )
                ]
            )
    else:
        text = texts.t('TICKET_REPLY_BLOCKED', '❌ Отвечать в этом обращении сейчас нельзя.')
    rows.append(
        [types.InlineKeyboardButton(text=texts.t('BACK_TO_MENU', '🏠 В главное меню'), callback_data='back_to_menu')]
    )
    return text, types.InlineKeyboardMarkup(inline_keyboard=rows)


async def reply_to_ticket(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    """Начать ответ на тикет"""
    texts = get_texts(db_user.language)
    try:
        ticket_id = int(callback.data.replace('reply_ticket_', ''))
    except ValueError:
        await callback.answer()
        return

    # Статус проверяем до того, как просить текст: раньше человек набирал ответ
    # и только потом узнавал, что обращение закрыто, — текст пропадал.
    ticket = await TicketCRUD.get_ticket_by_id(db, ticket_id, load_messages=False)
    if not ticket or ticket.user_id != db_user.id:
        await callback.answer(texts.t('TICKET_NOT_FOUND', 'Обращение не найдено.'), show_alert=True)
        return
    if ticket.status == TicketStatus.CLOSED.value or ticket.is_user_reply_blocked:
        text, keyboard = _ticket_reply_unavailable_view(texts, ticket)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        return

    await state.update_data(ticket_id=ticket_id)

    try:
        await callback.message.edit_text(
            texts.t('TICKET_REPLY_INPUT', 'Введите ваш ответ:'),
            reply_markup=get_ticket_reply_cancel_keyboard(db_user.language),
        )
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except (TelegramAPIError, AttributeError):
            pass
        await callback.message.answer(
            texts.t('TICKET_REPLY_INPUT', 'Введите ваш ответ:'),
            reply_markup=get_ticket_reply_cancel_keyboard(db_user.language),
        )

    await state.set_state(TicketStates.waiting_for_reply)
    await callback.answer()


async def handle_ticket_reply(message: types.Message, state: FSMContext, db_user: User, db: AsyncSession):
    # Проверяем, что пользователь в правильном состоянии
    current_state = await state.get_state()
    if current_state != TicketStates.waiting_for_reply:
        return

    async with _ticket_input_batch('reply', db_user.id, message) as batch:
        if batch is None:
            # Часть альбома или длинного текста — её заберёт первое сообщение пачки.
            return
        await _add_ticket_reply_from_batch(batch, state, db_user, db)


async def _add_ticket_reply_from_batch(batch: _TicketInputBatch, state: FSMContext, db_user: User, db: AsyncSession):
    """Обработать ответ на тикет"""
    messages = batch.take()
    message = messages[0]
    texts = get_texts(db_user.language)
    # Фото и видео для ответа пользователя, все части альбома и длинного текста.
    content = _ticket_input_content(messages)
    reply_text = content.text

    if len(reply_text) < 5 and not content.media_items:
        await message.answer(
            texts.t('TICKET_REPLY_TOO_SHORT', 'Ответ должен содержать минимум 5 символов. Попробуйте еще раз:')
        )
        return

    # Длинный ответ не обрезаем: пользователь должен получить его целиком.
    if len(reply_text) > TICKET_INPUT_MAX_LENGTH:
        await message.answer(
            texts.t(
                'TICKET_REPLY_TOO_LONG',
                'Ответ слишком длинный. Максимум {limit} символов. Сократите текст и отправьте еще раз:',
            ).format(limit=TICKET_INPUT_MAX_LENGTH)
        )
        return

    data = await state.get_data()
    ticket_id = data.get('ticket_id')

    if not ticket_id:
        await message.answer(
            texts.t('TICKET_REPLY_ERROR', '❌ Произошла ошибка при отправке ответа. Попробуйте позже.')
        )
        await state.clear()
        return

    try:
        # Проверяем, что тикет принадлежит пользователю и не закрыт
        ticket = await TicketCRUD.get_ticket_by_id(db, ticket_id, load_messages=False)
        if not ticket or ticket.user_id != db_user.id:
            await message.answer(texts.t('TICKET_NOT_FOUND', 'Обращение не найдено.'))
            await state.clear()
            return
        # Обращение могли закрыть, пока человек набирал ответ
        if ticket.status == TicketStatus.CLOSED.value or ticket.is_user_reply_blocked:
            text, keyboard = _ticket_reply_unavailable_view(texts, ticket)
            await message.answer(text, reply_markup=keyboard)
            await state.clear()
            return

        # Добавляем сообщение в тикет (длинный текст — несколькими сообщениями)
        media_fields = _ticket_media_fields(content)
        for chunk in _ticket_text_chunks(reply_text, TICKET_MESSAGE_MAX_LENGTH):
            await TicketMessageCRUD.add_message(db, ticket_id, db_user.id, chunk, is_from_admin=False, **media_fields)
            media_fields = {}
        # Части, пришедшие пока ответ сохранялся, — туда же
        late = _ticket_input_content(batch.take())
        await _append_ticket_messages(db, ticket_id, db_user.id, late)
        await state.clear()
        late_after_clear = _ticket_input_content(batch.take())
        await _append_ticket_messages(db, ticket_id, db_user.id, late_after_clear)

        await message.answer(
            texts.t('TICKET_REPLY_SENT', '✅ Ваш ответ отправлен!'),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('VIEW_TICKET', '👁️ Посмотреть обращение'),
                            callback_data=f'view_ticket_{ticket_id}',
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('BACK_TO_MENU', '🏠 В главное меню'), callback_data='back_to_menu'
                        )
                    ],
                ]
            ),
        )

        # Уведомить админов об ответе пользователя
        logger.info('Attempting to notify admins about ticket reply', ticket_id=ticket_id)
        notify_text = '\n'.join(part for part in (reply_text, late.text, late_after_clear.text) if part)
        await notify_admins_about_ticket_reply(
            ticket,
            notify_text,
            db,
            media_file_id=content.media_items[0]['file_id'] if content.media_items else None,
            media_type=content.media_items[0]['type'] if content.media_items else None,
        )

    except Exception as e:
        logger.error('Error adding ticket reply', error=e)
        await message.answer(
            texts.t('TICKET_REPLY_ERROR', '❌ Произошла ошибка при отправке ответа. Попробуйте позже.')
        )


async def close_ticket(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Закрыть тикет"""
    ticket_id = int(callback.data.replace('close_ticket_', ''))

    try:
        # Проверяем, что тикет принадлежит пользователю
        ticket = await TicketCRUD.get_ticket_by_id(db, ticket_id, load_messages=False)
        if not ticket or ticket.user_id != db_user.id:
            texts = get_texts(db_user.language)
            await callback.answer(texts.t('TICKET_NOT_FOUND', 'Обращение не найдено.'), show_alert=True)
            return

        # Запрещаем закрытие, если заблокирован для ответа? (не требуется) Закрываем тикет
        success = await TicketCRUD.close_ticket(db, ticket_id)

        if success:
            texts = get_texts(db_user.language)
            await callback.answer(texts.t('TICKET_CLOSED', '✅ Обращение закрыто.'), show_alert=True)

            # Обновляем inline-клавиатуру текущего сообщения (убираем кнопки)
            await callback.message.edit_reply_markup(
                reply_markup=get_ticket_view_keyboard(ticket_id, True, db_user.language)
            )
        else:
            texts = get_texts(db_user.language)
            await callback.answer(texts.t('TICKET_CLOSE_ERROR', '❌ Ошибка при закрытии обращения.'), show_alert=True)

    except Exception as e:
        logger.error('Error closing ticket', error=e)
        texts = get_texts(db_user.language)
        await callback.answer(texts.t('TICKET_CLOSE_ERROR', '❌ Ошибка при закрытии обращения.'), show_alert=True)


async def cancel_ticket_creation(callback: types.CallbackQuery, state: FSMContext, db_user: User):
    """Отменить создание тикета"""
    await state.clear()

    texts = get_texts(db_user.language)

    await callback.message.edit_text(
        texts.t('TICKET_CREATION_CANCELLED', 'Создание обращения отменено.'),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t('BACK_TO_SUPPORT', '⬅️ К поддержке'), callback_data='menu_support'
                    )
                ]
            ]
        ),
    )
    await callback.answer()


async def cancel_ticket_reply(callback: types.CallbackQuery, state: FSMContext, db_user: User):
    """Отменить ответ на тикет"""
    await state.clear()

    texts = get_texts(db_user.language)

    await callback.message.edit_text(
        texts.t('TICKET_REPLY_CANCELLED', 'Ответ отменен.'),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t('BACK_TO_TICKETS', '⬅️ К обращениям'), callback_data='my_tickets'
                    )
                ]
            ]
        ),
    )
    await callback.answer()


async def close_ticket_notification(callback: types.CallbackQuery, db_user: User):
    """Закрыть уведомление о тикете"""
    texts = get_texts(db_user.language)

    # Проверяем, доступно ли сообщение для удаления
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        # Message is too old to delete (>48h) — edit it instead
        try:
            await callback.message.edit_text(texts.t('NOTIFICATION_CLOSED', 'Уведомление закрыто.'))
        except TelegramBadRequest:
            pass
    await callback.answer(texts.t('NOTIFICATION_CLOSED', 'Уведомление закрыто.'))


def build_ticket_card_keyboard(ticket: Ticket, user: User | None, *, role: str):
    """Клавиатура карточки тикета по роли получателя ('admin' / 'moderator' / 'group').

    Для группового/супергруппа админ-чата ('group') — урезанный набор без
    FSM-кнопок: «Ответить»/«Блок по времени» в общем чате не работают из-за
    privacy mode бота, остаются надёжные URL/callback-кнопки. Той же клавиатурой
    карточка перерисовывается после действий в группе (закрыть, блок, разблок) —
    иначе туда попадал экран личной админки с мёртвыми кнопками и «⬅️ Назад».
    """
    from app.config import settings

    # В cabinet-режиме добавляем кнопку «открыть тикет в кабинете»: web_app в личке,
    # t.me Mini App диплинк в группе (где web_app недоступен). None — если не
    # cabinet-режим / кабинет не настроен / в группе нет зарегистрированного Mini App.
    cabinet_button = build_admin_ticket_cabinet_button(
        ticket.id,
        text=get_texts(settings.DEFAULT_LANGUAGE).t('OPEN_TICKET_IN_CABINET', '🗂 Открыть в кабинете'),
        in_group=(role == 'group'),
    )
    return get_ticket_notification_keyboard(
        ticket.id,
        user_id=user.id if user else None,
        telegram_id=user.telegram_id if user else None,
        username=user.username if user else None,
        is_closed=ticket.is_closed,
        is_user_blocked=getattr(ticket, 'is_user_reply_blocked', False),
        is_admin=(role == 'admin'),
        fsm_enabled=(role != 'group'),
        cabinet_button=cabinet_button,
        language=settings.DEFAULT_LANGUAGE,
    )


def _build_ticket_notification_keyboard(service: AdminNotificationService, ticket: Ticket, user: User | None):
    """Клавиатура уведомления о тикете; None только для роли 'none'
    (посторонний в личке / строковый chat_id)."""
    role = service.resolve_recipient_role()
    if role == 'none':
        return None
    return build_ticket_card_keyboard(ticket, user, role=role)


_CARD_BODY_LIMIT = 2500


async def _ticket_card_subscription_line(db: AsyncSession, user: User | None) -> str:
    """Короткая строка о подписке автора: чтобы не открывать профиль в админке."""
    if user is None:
        return ''
    try:
        from app.database.crud.subscription import get_all_subscriptions_by_user_id

        subscriptions = await get_all_subscriptions_by_user_id(db, user.id)
    except Exception as error:
        logger.debug('Ticket card: subscriptions unavailable', error=error)
        return ''
    if not subscriptions:
        line = '💳 Подписки нет'
    else:
        sub = subscriptions[0]
        status = sub.actual_status
        name = html.escape(
            getattr(getattr(sub, 'tariff', None), 'name', None) or ('Пробная' if sub.is_trial else 'Подписка')
        )
        if sub.end_date and sub.end_date.year >= 2090:
            until = 'навсегда'
        elif sub.end_date:
            until = ('до ' if status == 'active' else 'истекла ') + format_local_datetime(sub.end_date, '%d.%m.%Y')
        else:
            until = ''
        state = {'disabled': ' · отключена', 'limited': ' · лимит трафика'}.get(status, '')
        trial = ' (пробная)' if sub.is_trial and 'Проб' not in name else ''
        devices = f' · {sub.device_limit} устр.' if sub.device_limit else ''
        line = f'💳 {name}{trial} {until}{devices}{state}'.replace('  ', ' ')
    balance = (getattr(user, 'balance_kopeks', 0) or 0) // 100
    if balance > 0:
        line += f'\n💰 Баланс {balance} ₽'
    return line


def _is_group_recipient(service) -> bool:
    resolve = getattr(service, 'resolve_recipient_role', None)
    try:
        return callable(resolve) and resolve() == 'group'
    except Exception:
        return False


async def build_ticket_card_text(
    db: AsyncSession,
    ticket: Ticket,
    user: User | None,
    body: str,
    *,
    kind: str,
    in_group: bool,
) -> str:
    """Карточка обращения для админ-чата.

    kind: 'new' — новое обращение, 'reply' — новое сообщение в открытом,
    'waiting' — повтор карточки по команде /tickets в группе.
    Номер стоит в первой строке в виде «Обращение #N»: по нему ответ из
    группы (reply на карточку) находит тикет.
    """
    if kind == 'new':
        head = f'🎫 <b>Обращение #{ticket.id}</b> · новое'
    elif kind == 'waiting':
        since = ticket.updated_at or ticket.created_at
        when = f' с {format_local_datetime(since, "%d.%m %H:%M")}' if since else ''
        head = f'📌 <b>Обращение #{ticket.id}</b> · ждёт ответа{when}'
    else:
        head = f'💬 <b>Обращение #{ticket.id}</b> · новое сообщение'
    lines = [head]

    if user is not None:
        name = html.escape(user.full_name or '') or 'Без имени'
        link = format_username_link(user.username, '')
        handle = f' · {link}' if link else ''
        ident = user.telegram_id or user.email or f'#{user.id}'
        lines.append(f'👤 {name}{handle} · <code>{html.escape(str(ident))}</code>')
    sub_line = await _ticket_card_subscription_line(db, user)
    if sub_line:
        lines.append(sub_line)

    title = (ticket.title or '').strip()
    if title and kind in ('new', 'waiting'):
        lines.append('')
        lines.append(f'<b>{html.escape(title[:200])}</b>')
    body = (body or '').strip()
    if body:
        if len(body) > _CARD_BODY_LIMIT:
            body = body[: _CARD_BODY_LIMIT - 1] + '…'
        if kind == 'reply' or not title:
            lines.append('')
        lines.append(f'<blockquote>{html.escape(body)}</blockquote>')
    if in_group:
        lines.append('')
        lines.append('<i>↩️ Ответьте на это сообщение — ответ сразу уйдёт пользователю</i>')
    return '\n'.join(lines).replace('\n\n\n', '\n\n')


async def notify_admins_about_new_ticket(ticket: Ticket, db: AsyncSession):
    """Уведомить админов о новом тикете"""
    try:
        from app.config import settings

        if not settings.is_admin_notifications_enabled():
            logger.info(
                'Admin notifications disabled. Ticket created by user', ticket_id=ticket.id, user_id=ticket.user_id
            )
            return

        try:
            user = await get_user_by_id(db, ticket.user_id)
        except Exception:
            user = None

        # Первое сообщение: медиа и полный текст для карточки
        first_message = await TicketMessageCRUD.get_first_message(db, ticket.id)
        media_file_id = None
        media_type = None
        body = ''
        if first_message:
            media_file_id = first_message.media_file_id if first_message.has_media else None
            media_type = first_message.media_type if first_message.has_media else None
            body = first_message.message_text or ''

        from app.services.maintenance_service import maintenance_service

        bot = maintenance_service._bot or None
        if bot is None:
            logger.warning('Bot instance is not available for admin notifications')
            return

        service = AdminNotificationService(bot)

        # Определяем роль получателя до отправки (без I/O — данные в памяти).
        # В личном чате chat_id == telegram_id, что позволяет проверить права заранее.
        keyboard = _build_ticket_notification_keyboard(service, ticket, user)
        notification_text = await build_ticket_card_text(
            db, ticket, user, body, kind='new', in_group=_is_group_recipient(service)
        )

        await service.send_ticket_event_notification(
            notification_text, keyboard, media_file_id=media_file_id, media_type=media_type
        )
    except Exception as e:
        logger.error('Error notifying admins about new ticket', error=e)


async def notify_admins_about_ticket_reply(
    ticket: Ticket,
    reply_text: str,
    db: AsyncSession,
    *,
    media_file_id: str | None = None,
    media_type: str | None = None,
):
    """Уведомить админов об ответе пользователя на тикет"""
    logger.info('notify_admins_about_ticket_reply called for ticket', ticket_id=ticket.id)
    try:
        from app.config import settings

        if not settings.is_admin_notifications_enabled():
            logger.info('Admin notifications disabled. Reply to ticket', ticket_id=ticket.id)
            return

        try:
            user = await get_user_by_id(db, ticket.user_id)
        except Exception:
            user = None

        from app.services.maintenance_service import maintenance_service

        bot = maintenance_service._bot or None
        if bot is None:
            logger.warning('Bot instance is not available for admin notifications')
            return

        service = AdminNotificationService(bot)

        keyboard = _build_ticket_notification_keyboard(service, ticket, user)
        notification_text = await build_ticket_card_text(
            db, ticket, user, reply_text, kind='reply', in_group=_is_group_recipient(service)
        )

        result = await service.send_ticket_event_notification(
            notification_text, keyboard, media_file_id=media_file_id, media_type=media_type
        )
        logger.info('Ticket reply notification sent', ticket_id=ticket.id, result=result)
    except Exception as e:
        logger.error('Error notifying admins about ticket reply', error=e)


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков тикетов"""

    # Создание тикета (теперь без приоритета)
    dp.callback_query.register(show_ticket_priority_selection, F.data == 'create_ticket')

    dp.message.register(handle_ticket_title_input, TicketStates.waiting_for_title)

    dp.message.register(handle_ticket_message_input, TicketStates.waiting_for_message)

    # Просмотр тикетов
    dp.callback_query.register(show_my_tickets, F.data == 'my_tickets')
    dp.callback_query.register(show_my_tickets_closed, F.data == 'my_tickets_closed')
    dp.callback_query.register(show_my_tickets_closed, F.data.startswith('my_tickets_closed_page_'))

    dp.callback_query.register(view_ticket, F.data.startswith('view_ticket_') | F.data.startswith('ticket_view_page_'))

    # Вложения пользователя
    dp.callback_query.register(send_ticket_attachments, F.data.startswith('ticket_attachments_'))

    dp.callback_query.register(user_delete_message, F.data.startswith('user_delete_message_'))

    # Ответы на тикеты
    dp.callback_query.register(reply_to_ticket, F.data.startswith('reply_ticket_'))

    dp.message.register(handle_ticket_reply, TicketStates.waiting_for_reply)

    # Закрытие тикетов
    dp.callback_query.register(close_ticket, F.data.regexp(r'^close_ticket_\d+$'))

    # Отмена операций
    dp.callback_query.register(cancel_ticket_creation, F.data == 'cancel_ticket_creation')

    dp.callback_query.register(cancel_ticket_reply, F.data == 'cancel_ticket_reply')

    # Пагинация тикетов
    dp.callback_query.register(show_my_tickets, F.data.startswith('my_tickets_page_'))

    # Закрытие уведомлений
    dp.callback_query.register(close_ticket_notification, F.data.startswith('close_ticket_notification_'))
