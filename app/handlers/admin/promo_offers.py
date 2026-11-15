from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.discount_offer import upsert_discount_offer
from app.database.crud.promo_offer_log import list_promo_offer_logs
from app.database.crud.promo_offer_template import (
    ensure_default_templates,
    get_promo_offer_template_by_id,
    list_promo_offer_templates,
    update_promo_offer_template,
)
from app.database.crud.server_squad import (
    get_server_squad_by_uuid,
)
from app.database.crud.user import get_users_for_promo_segment
from app.database.models import (
    PromoOfferLog,
    PromoOfferTemplate,
    User,
)
from app.localization.texts import get_texts
from app.states import AdminStates
from app.utils.decorators import admin_required, error_handler
from app.utils.miniapp_buttons import build_miniapp_or_callback_button
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)


PROMO_OFFER_LOGS_PAGE_LIMIT = 10


async def _safe_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest as exc:
        if 'message to delete not found' not in str(exc).lower():
            logger.debug('Не удалось удалить сообщение администратора', exc=exc)
    except TelegramForbiddenError:
        logger.debug('Недостаточно прав для удаления сообщения администратора')


ACTION_LABEL_KEYS = {
    'claimed': 'ADMIN_PROMO_OFFER_LOGS_ACTION_CLAIMED',
    'consumed': 'ADMIN_PROMO_OFFER_LOGS_ACTION_CONSUMED',
    'disabled': 'ADMIN_PROMO_OFFER_LOGS_ACTION_DISABLED',
}


REASON_LABEL_KEYS = {
    'manual_charge': 'ADMIN_PROMO_OFFER_LOGS_REASON_MANUAL',
    'autopay_consumed': 'ADMIN_PROMO_OFFER_LOGS_REASON_AUTOPAY',
    'offer_expired': 'ADMIN_PROMO_OFFER_LOGS_REASON_EXPIRED',
    'test_access_expired': 'ADMIN_PROMO_OFFER_LOGS_REASON_TEST_EXPIRED',
}


OFFER_TYPE_CONFIG = {
    'test_access': {
        'icon': '🧪',
        'label_key': 'ADMIN_PROMO_OFFER_TEST_ACCESS',
        'default_label': 'Тестовые сервера',
        'allowed_segments': [
            ('paid_active', '🟢 Активные платные'),
            ('trial_active', '🎁 Активные триалы'),
        ],
        'effect_type': 'test_access',
    },
    'extend_discount': {
        'icon': '💎',
        'label_key': 'ADMIN_PROMO_OFFER_EXTEND',
        'default_label': 'Скидка на продление',
        'allowed_segments': [
            ('paid_active', '🟢 Активные платные'),
        ],
        'effect_type': 'percent_discount',
    },
    'purchase_discount': {
        'icon': '🎯',
        'label_key': 'ADMIN_PROMO_OFFER_PURCHASE',
        'default_label': 'Скидка на покупку',
        'allowed_segments': [
            ('paid_expired', '🔴 Истёкшие платные'),
            ('trial_expired', '🥶 Истёкшие триалы'),
            ('trial_active', '🎁 Активные триалы'),
        ],
        'effect_type': 'percent_discount',
    },
    'tariff_discount': {
        'icon': '👑',
        'label_key': 'ADMIN_PROMO_OFFER_TARIFF',
        'default_label': 'Скидка на один тариф (ULTIMA)',
        'allowed_segments': [
            ('all', '👥 Все пользователи'),
            ('paid_active', '🟢 Активные платные'),
            ('paid_expired', '🔴 Истёкшие платные'),
            ('trial_active', '🎁 Активные триалы'),
            ('trial_expired', '🥶 Истёкшие триалы'),
            ('no_subscription', '⚪ Без подписки'),
        ],
        'effect_type': 'percent_discount',
    },
}


def _render_template_text(
    template: PromoOfferTemplate,
    language: str,
    *,
    server_name: str | None = None,
) -> str:
    replacements = {
        'discount_percent': template.discount_percent,
        'valid_hours': template.valid_hours,
        'test_duration_hours': template.test_duration_hours or 0,
        'active_discount_hours': template.active_discount_hours or template.valid_hours,
    }

    if server_name is not None:
        replacements.setdefault('server_name', server_name)
    else:
        # Prevent KeyError if template expects server_name
        replacements.setdefault('server_name', '???')
    try:
        return template.message_text.format(**replacements)
    except Exception:  # pragma: no cover - fallback for invalid placeholders
        logger.warning('Не удалось форматировать текст промо-предложения', template_id=template.id)
        return template.message_text


async def _resolve_template_squad(
    db: AsyncSession,
    template: PromoOfferTemplate,
) -> tuple[str | None, str | None]:
    if template.offer_type != 'test_access':
        return None, None

    squads = template.test_squad_uuids or []
    if not squads:
        return None, None

    squad_uuid = str(squads[0])
    server = await get_server_squad_by_uuid(db, squad_uuid)
    server_name = server.display_name if server else None
    return squad_uuid, server_name


def _build_templates_keyboard(templates: Sequence[PromoOfferTemplate], language: str) -> InlineKeyboardMarkup:
    texts = get_texts(language)
    rows: list[list[InlineKeyboardButton]] = []
    for template in templates:
        config = OFFER_TYPE_CONFIG.get(template.offer_type, {})
        icon = config.get('icon', '📨')
        label = texts.t(config.get('label_key', ''), config.get('default_label', template.offer_type))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f'{icon} {label}',
                    callback_data=f'promo_offer_{template.id}',
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.t('ADMIN_PROMO_OFFER_LOGS', '📜 Лог операций'),
                callback_data='promo_offer_logs_page_1',
            )
        ]
    )
    rows.append([InlineKeyboardButton(text=texts.BACK, callback_data='admin_submenu_communications')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_offer_detail_keyboard(template: PromoOfferTemplate, language: str) -> InlineKeyboardMarkup:
    texts = get_texts(language)
    OFFER_TYPE_CONFIG.get(template.offer_type, {})
    rows: list[list[InlineKeyboardButton]] = []

    if template.offer_type != 'test_access':
        rows.append(
            [
                InlineKeyboardButton(text='⌛ Активна', callback_data=f'promo_offer_edit_active_{template.id}'),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(text='📬 Отправить', callback_data=f'promo_offer_send_menu_{template.id}'),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text=texts.BACK, callback_data='admin_promo_offers'),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


_TEMPLATE_ID_PATTERN = re.compile(r'promo_template_(?P<template_id>\d+)$')


def _format_promo_offer_log_entry(
    entry: PromoOfferLog,
    index: int,
    texts,
) -> str:
    timestamp = format_local_datetime(entry.created_at, '%d.%m.%Y %H:%M') if entry.created_at else '-'
    action_key = ACTION_LABEL_KEYS.get(entry.action, '')
    action_label = texts.get(action_key, entry.action.title())
    lines = [f'{index}. <b>{timestamp}</b> — {action_label}']

    user = entry.user
    if user:
        if user.username:
            username = f'@{user.username}'
        elif user.telegram_id:
            username = f'ID{user.telegram_id}'
        elif user.email:
            username = f'📧{user.email}'
        else:
            username = f'User#{user.id}'
        label = f'{username} (#{user.id})'
    elif entry.user_id:
        label = f'ID{entry.user_id}'
    else:
        label = texts.get('ADMIN_PROMO_OFFER_LOGS_UNKNOWN_USER', 'Неизвестный пользователь')

    lines.append(texts.get('ADMIN_PROMO_OFFER_LOGS_USER', '👤 {user}').format(user=html.escape(label)))

    if entry.percent:
        lines.append(texts.get('ADMIN_PROMO_OFFER_LOGS_PERCENT', '📉 Скидка: {percent}%').format(percent=entry.percent))

    effect_type = (entry.effect_type or '').lower()
    if effect_type:
        if effect_type == 'test_access':
            effect_label = texts.get('ADMIN_PROMO_OFFER_LOGS_EFFECT_TEST', '🧪 Тестовый доступ')
        else:
            effect_label = texts.get('ADMIN_PROMO_OFFER_LOGS_EFFECT_DISCOUNT', '💸 Скидка')
        lines.append(effect_label)

    if entry.source:
        lines.append(
            texts.get('ADMIN_PROMO_OFFER_LOGS_SOURCE', '🏷 Источник: {source}').format(source=html.escape(entry.source))
        )

    details: dict[str, object] = entry.details if isinstance(entry.details, dict) else {}
    reason_key = details.get('reason')
    if reason_key:
        reason_label = texts.get(REASON_LABEL_KEYS.get(reason_key, ''), '')
        if not reason_label:
            reason_label = texts.get(
                'ADMIN_PROMO_OFFER_LOGS_REASON_GENERIC',
                'ℹ️ Действие: {reason}',
            ).format(reason=html.escape(str(reason_key)))
        lines.append(reason_label)

    description = details.get('description')
    if description:
        lines.append(
            texts.get('ADMIN_PROMO_OFFER_LOGS_DESCRIPTION', '📝 {description}').format(
                description=html.escape(str(description))
            )
        )

    amount = details.get('amount_kopeks')
    if isinstance(amount, int):
        lines.append(
            texts.get('ADMIN_PROMO_OFFER_LOGS_AMOUNT', '💰 Сумма: {amount}').format(amount=texts.format_price(amount))
        )

    squad_uuid = details.get('squad_uuid')
    if squad_uuid:
        lines.append(
            texts.get('ADMIN_PROMO_OFFER_LOGS_SQUAD', '🌍 Сквад: {squad}').format(squad=html.escape(str(squad_uuid)))
        )

    new_squads = details.get('new_squads')
    if isinstance(new_squads, (list, tuple)):
        filtered = [html.escape(str(item)) for item in new_squads if item]
        if filtered:
            lines.append(
                texts.get('ADMIN_PROMO_OFFER_LOGS_NEW_SQUADS', '🌍 Новые сквады: {squads}').format(
                    squads=', '.join(filtered)
                )
            )

    return '\n'.join(lines)


def _build_logs_keyboard(page: int, total_pages: int, language: str) -> InlineKeyboardMarkup:
    texts = get_texts(language)
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text='⬅️',
                    callback_data=f'promo_offer_logs_page_{page - 1}',
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f'{page}/{total_pages}',
                callback_data=f'promo_offer_logs_page_{page}',
            )
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text='➡️',
                    callback_data=f'promo_offer_logs_page_{page + 1}',
                )
            )
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text=texts.BACK, callback_data='admin_promo_offers')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_send_keyboard(template: PromoOfferTemplate, language: str) -> InlineKeyboardMarkup:
    config = OFFER_TYPE_CONFIG.get(template.offer_type, {})
    segments = config.get('allowed_segments', [])
    texts = get_texts(language)
    rows: list[list[InlineKeyboardButton]] = []

    for segment, label in segments:
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f'promo_offer_send_{template.id}_{segment}',
                )
            ]
        )

    rows.append([InlineKeyboardButton(text=texts.BACK, callback_data=f'promo_offer_{template.id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _describe_offer(
    template: PromoOfferTemplate,
    language: str,
    *,
    server_name: str | None = None,
    server_uuid: str | None = None,
) -> str:
    texts = get_texts(language)
    config = OFFER_TYPE_CONFIG.get(template.offer_type, {})
    label = texts.t(config.get('label_key', ''), config.get('default_label', template.offer_type))
    icon = config.get('icon', '📨')

    lines = [f'{icon} <b>{html.escape(template.name)}</b>', '']
    lines.append(texts.t('ADMIN_PROMO_OFFER_TYPE', 'Тип: {label}').format(label=label))
    lines.append(texts.t('ADMIN_PROMO_OFFER_VALID', 'Срок действия: {hours} ч').format(hours=template.valid_hours))

    if template.offer_type != 'test_access':
        lines.append(
            texts.t(
                'ADMIN_PROMO_OFFER_DISCOUNT',
                'Доп. скидка: {percent}% (суммируется с промогруппой)',
            ).format(percent=template.discount_percent)
        )
        stack_note = texts.t(
            'ADMIN_PROMO_OFFER_STACKABLE_NOTE',
            'Скидка применяется один раз и добавляется к промогруппе.',
        )
        if stack_note:
            lines.append(stack_note)
        active_hours = template.active_discount_hours or 0
        if active_hours > 0:
            lines.append(
                texts.t(
                    'ADMIN_PROMO_OFFER_ACTIVE_DURATION',
                    'Скидка после активации действует {hours} ч.',
                ).format(hours=active_hours)
            )
    else:
        duration = template.test_duration_hours or 0
        lines.append(texts.t('ADMIN_PROMO_OFFER_TEST_DURATION', 'Доступ: {hours} ч').format(hours=duration))
        squads = template.test_squad_uuids or []
        if server_name:
            lines.append(texts.t('ADMIN_PROMO_OFFER_TEST_SQUAD_NAME', 'Сервер: {name}').format(name=server_name))
        elif squads:
            lines.append(
                texts.t('ADMIN_PROMO_OFFER_TEST_SQUADS', 'Сквады: {squads}').format(
                    squads=', '.join(str(item) for item in squads)
                )
            )
        elif server_uuid:
            lines.append(texts.t('ADMIN_PROMO_OFFER_TEST_SQUADS', 'Сквады: {squads}').format(squads=server_uuid))
        else:
            lines.append(texts.t('ADMIN_PROMO_OFFER_TEST_SQUADS_EMPTY', 'Сквады: не указаны'))

    allowed_segments = config.get('allowed_segments', [])
    if allowed_segments:
        segment_labels = [label for _, label in allowed_segments]
        lines.append('')
        lines.append(texts.t('ADMIN_PROMO_OFFER_ALLOWED', 'Доступные категории:'))
        lines.extend(segment_labels)

    lines.append('')
    lines.append(texts.t('ADMIN_PROMO_OFFER_PREVIEW', 'Предпросмотр:'))
    lines.append(
        _render_template_text(
            template,
            language,
            server_name=server_name,
        )
    )

    return '\n'.join(lines)


@admin_required
@error_handler
async def show_promo_offers_menu(callback: CallbackQuery, db_user: User, db: AsyncSession):
    await ensure_default_templates(db, created_by=db_user.id)
    templates = await list_promo_offer_templates(db)
    texts = get_texts(db_user.language)
    header = texts.t('ADMIN_PROMO_OFFERS_TITLE', '🎯 <b>Промо-предложения</b>\n\nВыберите предложение для настройки:')
    await callback.message.edit_text(
        header,
        reply_markup=_build_templates_keyboard(templates, db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_promo_offer_details(callback: CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    try:
        template_id = int(callback.data.split('_')[-1])
    except (ValueError, AttributeError):
        await callback.answer('❌ Неверный идентификатор', show_alert=True)
        return

    template = await get_promo_offer_template_by_id(db, template_id)
    if not template:
        await callback.answer('❌ Предложение не найдено', show_alert=True)
        return

    await state.update_data(selected_promo_offer=template.id)
    squad_uuid, squad_name = await _resolve_template_squad(db, template)
    description = _describe_offer(
        template,
        db_user.language,
        server_name=squad_name,
        server_uuid=squad_uuid,
    )
    await callback.message.edit_text(
        description,
        reply_markup=_build_offer_detail_keyboard(template, db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_promo_offer_logs(callback: CallbackQuery, db_user: User, db: AsyncSession):
    try:
        if '_page_' in callback.data:
            page = int(callback.data.split('_page_')[-1])
        else:
            page = 1
    except (ValueError, AttributeError):
        page = 1

    page = max(page, 1)

    limit = PROMO_OFFER_LOGS_PAGE_LIMIT
    offset = (page - 1) * limit
    logs, total = await list_promo_offer_logs(db, offset=offset, limit=limit)
    total_pages = max(1, (total + limit - 1) // limit)

    if page > total_pages and total > 0:
        page = total_pages
        offset = (page - 1) * limit
        logs, _ = await list_promo_offer_logs(db, offset=offset, limit=limit)

    texts = get_texts(db_user.language)
    header = texts.t(
        'ADMIN_PROMO_OFFER_LOGS_TITLE',
        '📜 <b>Лог операций промо-предложений</b>',
    )

    if logs:
        message_lines = [
            header,
            texts.get(
                'ADMIN_PROMO_OFFER_LOGS_PAGINATION',
                'Страница {page}/{total}',
            ).format(page=page, total=total_pages),
            '',
        ]
        for index, entry in enumerate(logs, start=offset + 1):
            message_lines.append(_format_promo_offer_log_entry(entry, index, texts))
            message_lines.append('')
        message_text = '\n'.join(message_lines).rstrip()
    else:
        message_text = '\n'.join(
            [
                header,
                '',
                texts.get(
                    'ADMIN_PROMO_OFFER_LOGS_EMPTY_BODY',
                    'Записей пока нет.',
                ),
            ]
        )

    keyboard = _build_logs_keyboard(page, total_pages, db_user.language)
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode='HTML',
    )
    await callback.answer()


async def _prompt_edit(callback: CallbackQuery, state: FSMContext, template_id: int, prompt: str, new_state):
    await state.update_data(
        selected_promo_offer=template_id,
        promo_edit_message_id=callback.message.message_id,
        promo_edit_chat_id=callback.message.chat.id,
    )
    await callback.message.edit_text(prompt)
    await state.set_state(new_state)
    await callback.answer()


@admin_required
@error_handler
async def prompt_edit_active_duration(callback: CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    template_id = int(callback.data.split('_')[-1])
    texts = get_texts(db_user.language)
    prompt = texts.t(
        'ADMIN_PROMO_OFFER_PROMPT_ACTIVE_DURATION',
        'Введите срок действия активированной скидки (в часах):',
    )
    await _prompt_edit(
        callback,
        state,
        template_id,
        prompt,
        AdminStates.editing_promo_offer_active_duration,
    )


async def _handle_edit_field(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    db_user: User,
    field: str,
):
    data = await state.get_data()
    template_id = data.get('selected_promo_offer')
    if not template_id:
        await _safe_delete_message(message)
        await message.answer('❌ Не удалось определить предложение. Повторите действие.')
        await state.clear()
        return

    template = await get_promo_offer_template_by_id(db, int(template_id))
    if not template:
        await _safe_delete_message(message)
        await message.answer('❌ Предложение не найдено.')
        await state.clear()
        return

    value = message.text.strip()
    try:
        if field == 'message_text':
            await update_promo_offer_template(db, template, message_text=value)
        elif field == 'button_text':
            await update_promo_offer_template(db, template, button_text=value)
        elif field == 'valid_hours':
            hours = max(1, int(value))
            await update_promo_offer_template(db, template, valid_hours=hours)
        elif field == 'discount_percent':
            percent = max(0, min(100, int(value)))
            await update_promo_offer_template(db, template, discount_percent=percent)
        elif field == 'active_discount_hours':
            hours = max(1, int(value))
            await update_promo_offer_template(db, template, active_discount_hours=hours)
        elif field == 'test_duration_hours':
            hours = max(1, int(value))
            await update_promo_offer_template(db, template, test_duration_hours=hours)
        elif field == 'test_squad_uuids':
            if value.lower() in {'clear', 'очистить'}:
                squads: list[str] = []
            else:
                squads = [item for item in re.split(r'[\s,]+', value) if item]
            await update_promo_offer_template(db, template, test_squad_uuids=squads)
        else:
            raise ValueError('Unsupported field')
    except ValueError:
        await _safe_delete_message(message)
        await message.answer('❌ Некорректное значение. Попробуйте снова.')
        return

    edit_message_id = data.get('promo_edit_message_id')
    edit_chat_id = data.get('promo_edit_chat_id', message.chat.id)

    await state.clear()
    updated_template = await get_promo_offer_template_by_id(db, template.id)
    if not updated_template:
        await _safe_delete_message(message)
        await message.answer('❌ Предложение не найдено после обновления.')
        return

    squad_uuid, squad_name = await _resolve_template_squad(db, updated_template)
    description = _describe_offer(
        updated_template,
        db_user.language,
        server_name=squad_name,
        server_uuid=squad_uuid,
    )
    reply_markup = _build_offer_detail_keyboard(updated_template, db_user.language)

    if edit_message_id:
        try:
            await message.bot.edit_message_text(
                description,
                chat_id=edit_chat_id,
                message_id=edit_message_id,
                reply_markup=reply_markup,
                parse_mode='HTML',
            )
        except TelegramBadRequest as exc:
            error_text = str(exc).lower()
            if 'there is no text in the message to edit' in error_text:
                logger.debug('Сообщение промо без текста, пересылаем обновлённую версию')
                try:
                    await message.bot.delete_message(chat_id=edit_chat_id, message_id=edit_message_id)
                except TelegramBadRequest:
                    logger.debug('Не удалось удалить сообщение промо без текста')
            else:
                logger.warning('Не удалось обновить сообщение редактирования промо', exc=exc)
            await message.answer(description, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await message.answer(description, reply_markup=reply_markup, parse_mode='HTML')

    await _safe_delete_message(message)


@admin_required
@error_handler
async def show_send_segments(callback: CallbackQuery, db_user: User, db: AsyncSession):
    template_id = int(callback.data.split('_')[-1])
    template = await get_promo_offer_template_by_id(db, template_id)
    if not template:
        await callback.answer('❌ Предложение не найдено', show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=_build_send_keyboard(template, db_user.language))
    await callback.answer()


async def _send_prepaid_tariff_offer(
    bot,
    new_db,
    template: PromoOfferTemplate,
    user: User,
    fallback_language,
    active_minutes: int | None = None,
    ignore_preferences: bool = False,
) -> bool:
    """Предложение «скидка на один тариф», активное сразу при отправке (без шага «Забрать»)."""
    from datetime import timedelta

    from app.database.crud.discount_offer import mark_offer_claimed
    from app.utils.notification_prefs import is_promo_offers_enabled
    from app.utils.promo_offer import offer_discount_source

    if not user.telegram_id:
        return False
    # ignore_preferences: человек сам нажал ссылку на предложение (канал), настройка рассылок тут не при чём.
    if not ignore_preferences and (not settings.is_notifications_enabled() or not is_promo_offers_enabled(user)):
        return False

    fresh = await new_db.get(User, user.id)
    if fresh is None:
        return False
    # Защит от повтора нет: предложение уходит каждый раз, когда админ нажимает «отправить».
    # Прежнюю скидку запоминаем только чтобы вернуть её, если сообщение не доставится.
    prev_percent = fresh.promo_offer_discount_percent
    prev_source = fresh.promo_offer_discount_source
    prev_expires = fresh.promo_offer_discount_expires_at

    hours = int(template.active_discount_hours or template.valid_hours or 1)
    offer = await upsert_discount_offer(
        new_db,
        user_id=fresh.id,
        subscription_id=None,
        notification_type=f'promo_template_{template.id}',
        discount_percent=template.discount_percent,
        bonus_amount_kopeks=0,
        valid_hours=hours,
        effect_type='percent_discount',
        extra_data={
            'template_id': template.id,
            'offer_type': template.offer_type,
            'active_discount_hours': hours,
        },
    )
    now = datetime.now(UTC)
    fresh.promo_offer_discount_percent = int(template.discount_percent)
    fresh.promo_offer_discount_source = offer_discount_source(offer)
    # active_minutes — точный срок для разовых рассылок (например, 30 минут); иначе часы шаблона.
    lifetime = timedelta(minutes=active_minutes) if active_minutes else timedelta(hours=hours)
    fresh.promo_offer_discount_expires_at = now + lifetime
    await mark_offer_claimed(new_db, offer, details={'context': 'prepaid_tariff_offer'})

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=template.button_text,
                    callback_data=f'tariff_select:{int(settings.PROMO_OFFER_TARIFF_ID)}',
                    style='primary',
                )
            ]
        ]
    )
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=_render_template_text(template, user.language or fallback_language),
            reply_markup=keyboard,
            parse_mode='HTML',
        )
    except Exception:
        # Не доставили: возвращаем скидку, какой она была до этой отправки.
        fresh.promo_offer_discount_percent = prev_percent or 0
        fresh.promo_offer_discount_source = prev_source
        fresh.promo_offer_discount_expires_at = prev_expires
        await new_db.commit()
        raise
    return True


async def _send_offer_to_users(
    bot,
    template: PromoOfferTemplate,
    db_user: User,
    db: AsyncSession,
    users: Sequence[User],
    *,
    squad_name: str | None,
    effect_type: str,
    active_minutes: int | None = None,
) -> tuple[int, int]:
    from app.database.database import AsyncSessionLocal

    sent = 0
    failed = 0
    already = 0  # пропущены: предложение уже было у человека или действует другая скидка

    # Ограничение на количество одновременных отправок
    semaphore = asyncio.Semaphore(20)

    async def send_single_offer(user):
        """Отправляет одно предложение с семафором ограничения"""
        from app.utils.notification_prefs import is_promo_offers_enabled

        # Оффер создаётся, а уведомление уходит на подтверждённую почту (активация — в кабинете).
        if not user.telegram_id and not (user.email and user.email_verified):
            logger.debug('У пользователя нет ни Telegram, ни подтверждённого email — промо пропущено', user_id=user.id)
            return False

        async with semaphore:
            try:
                # Используем отдельную сессию для изоляции транзакции
                async with AsyncSessionLocal() as new_db:
                    if template.offer_type == 'tariff_discount':
                        return await _send_prepaid_tariff_offer(
                            bot, new_db, template, user, db_user.language, active_minutes
                        )
                    _offer_sub = getattr(user, 'subscription', None)
                    _offer_sub_id = _offer_sub.id if _offer_sub else None
                    offer_record = await upsert_discount_offer(
                        new_db,
                        user_id=user.id,
                        subscription_id=_offer_sub_id,
                        notification_type=f'promo_template_{template.id}',
                        discount_percent=template.discount_percent,
                        bonus_amount_kopeks=0,
                        valid_hours=template.valid_hours,
                        effect_type=effect_type,
                        extra_data={
                            'template_id': template.id,
                            'offer_type': template.offer_type,
                            'test_duration_hours': template.test_duration_hours,
                            'test_squad_uuids': template.test_squad_uuids,
                            'active_discount_hours': template.active_discount_hours,
                        },
                    )

                    message_text = _render_template_text(
                        template,
                        user.language or db_user.language,
                        server_name=squad_name,
                    )

                    # Настройка уведомлений глушит СООБЩЕНИЕ, но не саму скидку:
                    # оффер уже создан выше и остаётся доступным в кабинете и
                    # миниаппе. Так же ведёт себя кабинетная рассылка
                    # (`admin_promo_offers.broadcast`), и расходиться они не должны.
                    if not settings.is_notifications_enabled() or not is_promo_offers_enabled(user):
                        logger.debug(
                            'Промо-оффер создан, уведомление подавлено настройками',
                            user_id=user.id,
                        )
                        return True

                    if not user.telegram_id:
                        # Email-only юзер: тот же текст на почту, кнопке «Получить»
                        # соответствует ссылка на кабинет внутри шаблона письма.
                        from app.services.promo_offer_email import send_promo_offer_email

                        return await send_promo_offer_email(
                            email=user.email,
                            language=user.language or db_user.language,
                            username=user.first_name or user.username or '',
                            user_id=user.id,
                            message_text=message_text,
                            valid_hours=template.valid_hours,
                            discount_percent=template.discount_percent or 0,
                        )

                    user_texts = get_texts(user.language or db_user.language)
                    keyboard_rows: list[list[InlineKeyboardButton]] = [
                        [
                            build_miniapp_or_callback_button(
                                text=template.button_text,
                                callback_data=f'claim_discount_{offer_record.id}',
                            )
                        ]
                    ]

                    keyboard_rows.append(
                        [
                            InlineKeyboardButton(
                                text=user_texts.t('PROMO_OFFER_CLOSE', '❌ Закрыть'),
                                callback_data='promo_offer_close',
                            )
                        ]
                    )

                    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=message_text,
                        reply_markup=keyboard,
                        parse_mode='HTML',
                    )
                    return True
            except TelegramForbiddenError:
                # Человек заблокировал бота: ожидаемо при массовой отправке (были тысячи трассировок за день).
                logger.debug('Предложение не доставлено: бот заблокирован', telegram_id=user.telegram_id or user.id)
                return False
            except TelegramBadRequest as exc:
                logger.warning(
                    'Не удалось отправить предложение пользователю',
                    telegram_id=user.telegram_id or user.id,
                    error=str(exc)[:200],
                )
                return False
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(
                    'Ошибка рассылки промо предложения пользователю', telegram_id=user.telegram_id or user.id, exc=exc
                )
                return False

    # Отправляем предложения пакетами для эффективности
    batch_size = 100
    for i in range(0, len(users), batch_size):
        batch = users[i : i + batch_size]
        tasks = [send_single_offer(user) for user in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result is None:  # пропуск: предложение уже было или есть другая скидка
                already += 1
            elif isinstance(result, bool):  # Успешно или неуспешно
                if result:
                    sent += 1
                else:
                    failed += 1
            elif isinstance(result, Exception):  # Ошибка выполнения задачи
                failed += 1

        # Небольшая задержка между пакетами для снижения нагрузки на API
        await asyncio.sleep(0.1)

    return sent, failed, already


@admin_required
@error_handler
async def send_offer_to_segment(callback: CallbackQuery, db_user: User, db: AsyncSession):
    try:
        prefix = 'promo_offer_send_'
        if not callback.data.startswith(prefix):
            raise ValueError('invalid prefix')
        data = callback.data[len(prefix) :]
        template_id_str, segment = data.split('_', 1)
        template_id = int(template_id_str)
    except (ValueError, AttributeError):
        await callback.answer('❌ Некорректные данные', show_alert=True)
        return

    template = await get_promo_offer_template_by_id(db, template_id)
    if not template:
        await callback.answer('❌ Предложение не найдено', show_alert=True)
        return

    config = OFFER_TYPE_CONFIG.get(template.offer_type, {})
    squad_uuid, squad_name = await _resolve_template_squad(db, template)
    allowed_segments = {seg for seg, _ in config.get('allowed_segments', [])}
    if segment not in allowed_segments:
        await callback.answer('⚠️ Нельзя отправить это предложение выбранной категории', show_alert=True)
        return

    texts = get_texts(db_user.language)
    await callback.answer(texts.t('ADMIN_PROMO_OFFER_SENDING', 'Начинаем рассылку...'), show_alert=True)

    users = await get_users_for_promo_segment(db, segment)
    initial_count = len(users)

    if template.offer_type == 'test_access' and squad_uuid:
        filtered_users: list[User] = []
        for user in users:
            subscription = getattr(user, 'subscription', None)
            connected = set(subscription.connected_squads or []) if subscription else set()
            if squad_uuid in connected:
                continue
            filtered_users.append(user)
        users = filtered_users

    if not users:
        await callback.message.answer(texts.t('ADMIN_PROMO_OFFER_NO_USERS', 'Подходящих пользователей не найдено.'))
        return

    skipped = initial_count - len(users)
    effect_type = config.get('effect_type', 'percent_discount')

    # Отправка идёт фоновым заданием в базе: переживает перезапуск бота и не держит соединение обработчика.
    from app.services.mass_send_service import mass_send_service

    job_id = await mass_send_service.create_promo_offer_job(
        template_id=template.id,
        segment=segment,
        admin_user_id=db_user.id,
        chat_id=callback.message.chat.id,
        language=db_user.language,
        user_ids=[user.id for user in users],
        effect_type=effect_type,
        squad_name=squad_name,
        skipped=skipped,
    )
    started = texts.t(
        'ADMIN_PROMO_OFFER_QUEUED',
        '📬 Рассылка запущена: {count} получателей (задание {job_id}).\n'
        'Итог придёт сообщением. Если бот перезапустится, отправка продолжится сама.',
    ).format(count=len(users), job_id=job_id)
    await callback.message.edit_text(
        started,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.t('ADMIN_PROMO_OFFER_BACK_TO_LIST', '⬅️ К промопредложениям'),
                        callback_data='admin_promo_offers',
                    )
                ]
            ]
        ),
        parse_mode='HTML',
    )


async def process_edit_active_duration_hours(message: Message, state: FSMContext, db: AsyncSession, db_user: User):
    await _handle_edit_field(message, state, db, db_user, 'active_discount_hours')


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_promo_offers_menu, F.data == 'admin_promo_offers')
    dp.callback_query.register(prompt_edit_active_duration, F.data.startswith('promo_offer_edit_active_'))
    dp.callback_query.register(show_send_segments, F.data.startswith('promo_offer_send_menu_'))
    dp.callback_query.register(send_offer_to_segment, F.data.startswith('promo_offer_send_'))
    dp.callback_query.register(show_promo_offer_logs, F.data.regexp(r'^promo_offer_logs_page_\d+$'))
    dp.callback_query.register(show_promo_offer_details, F.data.startswith('promo_offer_'))

    dp.message.register(process_edit_active_duration_hours, AdminStates.editing_promo_offer_active_duration)
