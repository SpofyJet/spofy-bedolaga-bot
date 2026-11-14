import html
import re

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.campaign import (
    create_campaign,
    get_campaign_by_id,
    get_campaign_by_start_parameter,
    get_campaign_statistics,
    get_campaigns_count,
    get_campaigns_list,
    get_campaigns_overview,
)
from app.database.models import User
from app.keyboards.admin import (
    get_admin_campaigns_keyboard,
    get_admin_pagination_keyboard,
    get_campaign_bonus_type_keyboard,
    get_campaign_management_keyboard,
)
from app.localization.texts import Texts, get_texts
from app.states import AdminStates
from app.utils.decorators import admin_required, error_handler
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)

_CAMPAIGN_PARAM_REGEX = re.compile(r'^[A-Za-z0-9_-]{3,32}$')
_CAMPAIGNS_PAGE_SIZE = 5


def _format_campaign_summary(campaign, texts) -> str:
    status = '🟢 Активна' if campaign.is_active else '⚪️ Выключена'

    if campaign.is_balance_bonus:
        bonus_text = texts.format_price(campaign.balance_bonus_kopeks)
        bonus_info = f'💰 Бонус на баланс: <b>{bonus_text}</b>'
    elif campaign.is_subscription_bonus:
        traffic_text = texts.format_traffic(campaign.subscription_traffic_gb or 0)
        device_limit = campaign.subscription_device_limit
        if device_limit is None:
            device_limit = settings.DEFAULT_DEVICE_LIMIT
        bonus_info = (
            f'📱 Пробная подписка: <b>{campaign.subscription_duration_days or 0} д.</b>\n'
            f'🌐 Трафик: <b>{traffic_text}</b>\n'
            f'📱 Устройства: <b>{Texts.format_device_limit(device_limit)}</b>'
        )
    elif campaign.is_tariff_bonus:
        tariff_name = 'Не выбран'
        if hasattr(campaign, 'tariff') and campaign.tariff:
            tariff_name = campaign.tariff.name
        bonus_info = f'🎁 Тариф: <b>{tariff_name}</b>\n📅 Длительность: <b>{campaign.tariff_duration_days or 0} д.</b>'
    elif campaign.is_none_bonus:
        bonus_info = '🔗 Только ссылка (без награды)'
    else:
        bonus_info = '❓ Неизвестный тип бонуса'

    return (
        f'<b>{html.escape(campaign.name)}</b>\n'
        f'Стартовый параметр: <code>{html.escape(campaign.start_parameter)}</code>\n'
        f'Статус: {status}\n'
        f'{bonus_info}\n'
    )


async def _get_bot_deep_link(callback: types.CallbackQuery, start_parameter: str) -> str:
    bot = await callback.bot.get_me()
    return f'https://t.me/{bot.username}?start={start_parameter}'


async def _get_bot_deep_link_from_message(message: types.Message, start_parameter: str) -> str:
    bot = await message.bot.get_me()
    return f'https://t.me/{bot.username}?start={start_parameter}'


@admin_required
@error_handler
async def show_campaigns_menu(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    overview = await get_campaigns_overview(db)

    text = (
        '📣 <b>Рекламные кампании</b>\n\n'
        f'Всего кампаний: <b>{overview["total"]}</b>\n'
        f'Активных: <b>{overview["active"]}</b> | Выключены: <b>{overview["inactive"]}</b>\n'
        f'Регистраций: <b>{overview["registrations"]}</b>\n'
        f'Выдано баланса: <b>{texts.format_price(overview["balance_total"])}</b>\n'
        f'Выдано подписок: <b>{overview["subscription_total"]}</b>'
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_campaigns_keyboard(db_user.language),
    )
    await callback.answer()


@admin_required
@error_handler
async def show_campaigns_overall_stats(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    overview = await get_campaigns_overview(db)

    text = ['📊 <b>Общая статистика кампаний</b>\n']
    text.append(f'Всего кампаний: <b>{overview["total"]}</b>')
    text.append(f'Активны: <b>{overview["active"]}</b>, выключены: <b>{overview["inactive"]}</b>')
    text.append(f'Всего регистраций: <b>{overview["registrations"]}</b>')
    text.append(f'Суммарно выдано баланса: <b>{texts.format_price(overview["balance_total"])}</b>')
    text.append(f'Выдано подписок: <b>{overview["subscription_total"]}</b>')

    await callback.message.edit_text(
        '\n'.join(text),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_campaigns')]]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def show_campaigns_list(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    page = 1
    if callback.data.startswith('admin_campaigns_list_page_'):
        try:
            page = int(callback.data.split('_')[-1])
        except ValueError:
            page = 1

    offset = (page - 1) * _CAMPAIGNS_PAGE_SIZE
    campaigns = await get_campaigns_list(
        db,
        offset=offset,
        limit=_CAMPAIGNS_PAGE_SIZE,
    )
    total = await get_campaigns_count(db)
    total_pages = max(1, (total + _CAMPAIGNS_PAGE_SIZE - 1) // _CAMPAIGNS_PAGE_SIZE)

    if not campaigns:
        await callback.message.edit_text(
            '❌ Рекламные кампании не найдены.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='➕ Создать', callback_data='admin_campaigns_create')],
                    [types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_campaigns')],
                ]
            ),
        )
        await callback.answer()
        return

    text_lines = ['📋 <b>Список кампаний</b>\n']

    for campaign in campaigns:
        # Access from instance dict to avoid MissingGreenlet on lazy load
        regs = sa_inspect(campaign).dict.get('registrations', []) or []
        registrations = len(regs)
        total_balance = sum(r.balance_bonus_kopeks or 0 for r in regs)
        status = '🟢' if campaign.is_active else '⚪'
        line = (
            f'{status} <b>{html.escape(campaign.name)}</b> — <code>{html.escape(campaign.start_parameter)}</code>\n'
            f'   Регистраций: {registrations}, баланс: {texts.format_price(total_balance)}'
        )
        if campaign.is_subscription_bonus:
            line += f', подписка: {campaign.subscription_duration_days or 0} д.'
        else:
            line += ', бонус: баланс'
        text_lines.append(line)

    keyboard_rows = [
        [
            types.InlineKeyboardButton(
                text=f'🔍 {campaign.name}',
                callback_data=f'admin_campaign_manage_{campaign.id}',
            )
        ]
        for campaign in campaigns
    ]

    pagination = get_admin_pagination_keyboard(
        current_page=page,
        total_pages=total_pages,
        callback_prefix='admin_campaigns_list',
        back_callback='admin_campaigns',
        language=db_user.language,
    )

    keyboard_rows.extend(pagination.inline_keyboard)

    await callback.message.edit_text(
        '\n'.join(text_lines),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )
    await callback.answer()


@admin_required
@error_handler
async def show_campaign_detail(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    campaign_id = int(callback.data.split('_')[-1])
    campaign = await get_campaign_by_id(db, campaign_id)

    if not campaign:
        await callback.answer('❌ Кампания не найдена', show_alert=True)
        return

    texts = get_texts(db_user.language)
    stats = await get_campaign_statistics(db, campaign_id)
    deep_link = await _get_bot_deep_link(callback, campaign.start_parameter)

    text = ['📣 <b>Управление кампанией</b>\n']
    text.append(_format_campaign_summary(campaign, texts))
    text.append(f'🔗 Ссылка: <code>{deep_link}</code>')
    text.append('\n📊 <b>Статистика</b>')
    text.append(f'• Регистраций: <b>{stats["registrations"]}</b>')
    text.append(f'• Выдано баланса: <b>{texts.format_price(stats["balance_issued"])}</b>')
    text.append(f'• Выдано подписок: <b>{stats["subscription_issued"]}</b>')
    text.append(f'• Доход: <b>{texts.format_price(stats["total_revenue_kopeks"])}</b>')
    text.append(f'• Получили триал: <b>{stats["trial_users_count"]}</b> (активно: {stats["active_trials_count"]})')
    text.append(
        '• Конверсий в оплату: '
        f'<b>{stats["conversion_count"]}</b>'
        f' / пользователей с оплатой: {stats["paid_users_count"]}'
    )
    text.append(f'• Конверсия в оплату: <b>{stats["conversion_rate"]:.1f}%</b>')
    text.append(f'• Конверсия триала: <b>{stats["trial_conversion_rate"]:.1f}%</b>')
    text.append(f'• Средний доход на пользователя: <b>{texts.format_price(stats["avg_revenue_per_user_kopeks"])}</b>')
    text.append(f'• Средний первый платеж: <b>{texts.format_price(stats["avg_first_payment_kopeks"])}</b>')
    if stats['last_registration']:
        text.append(f'• Последняя: {format_local_datetime(stats["last_registration"], "%d.%m.%Y %H:%M")}')

    await callback.message.edit_text(
        '\n'.join(text),
        reply_markup=get_campaign_management_keyboard(campaign.id, campaign.is_active, db_user.language),
    )
    await callback.answer()


@admin_required
@error_handler
async def show_campaign_stats(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    campaign_id = int(callback.data.split('_')[-1])
    campaign = await get_campaign_by_id(db, campaign_id)
    if not campaign:
        await callback.answer('❌ Кампания не найдена', show_alert=True)
        return

    texts = get_texts(db_user.language)
    stats = await get_campaign_statistics(db, campaign_id)

    text = ['📊 <b>Статистика кампании</b>\n']
    text.append(_format_campaign_summary(campaign, texts))
    text.append(f'Регистраций: <b>{stats["registrations"]}</b>')
    text.append(f'Выдано баланса: <b>{texts.format_price(stats["balance_issued"])}</b>')
    text.append(f'Выдано подписок: <b>{stats["subscription_issued"]}</b>')
    if stats['last_registration']:
        text.append(f'Последняя регистрация: {format_local_datetime(stats["last_registration"], "%d.%m.%Y %H:%M")}')

    await callback.message.edit_text(
        '\n'.join(text),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text='⬅️ Назад',
                        callback_data=f'admin_campaign_manage_{campaign_id}',
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def start_campaign_creation(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    await state.clear()
    await callback.message.edit_text(
        '🆕 <b>Создание рекламной кампании</b>\n\nВведите название кампании:',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_campaigns')]]
        ),
    )
    await state.set_state(AdminStates.creating_campaign_name)
    await callback.answer()


@admin_required
@error_handler
async def process_campaign_name(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    name = message.text.strip()
    if len(name) < 3 or len(name) > 100:
        await message.answer('❌ Название должно содержать от 3 до 100 символов. Попробуйте снова.')
        return

    await state.update_data(campaign_name=name)
    await state.set_state(AdminStates.creating_campaign_start)
    await message.answer(
        '🔗 Теперь введите параметр старта (латинские буквы, цифры, - или _):',
    )


@admin_required
@error_handler
async def process_campaign_start_parameter(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    start_param = message.text.strip()
    if not _CAMPAIGN_PARAM_REGEX.match(start_param):
        await message.answer('❌ Разрешены только латинские буквы, цифры, символы - и _. Длина 3-32 символа.')
        return

    existing = await get_campaign_by_start_parameter(db, start_param)
    if existing:
        await message.answer('❌ Кампания с таким параметром уже существует. Введите другой параметр.')
        return

    await state.update_data(campaign_start_parameter=start_param)
    await state.set_state(AdminStates.creating_campaign_bonus)
    await message.answer(
        '🎯 Выберите тип бонуса для кампании:',
        reply_markup=get_campaign_bonus_type_keyboard(db_user.language),
    )


@admin_required
@error_handler
async def select_campaign_bonus_type(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    # Определяем тип бонуса из callback_data
    if callback.data.endswith('balance'):
        bonus_type = 'balance'
    elif callback.data.endswith('none'):
        bonus_type = 'none'
    else:
        bonus_type = 'balance'

    await state.update_data(campaign_bonus_type=bonus_type)

    if bonus_type == 'balance':
        await state.set_state(AdminStates.creating_campaign_balance)
        await callback.message.edit_text(
            '💰 Введите сумму бонуса на баланс (в рублях):',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_campaigns')]]
            ),
        )
    elif bonus_type == 'none':
        # Сразу создаём кампанию без бонуса
        data = await state.get_data()
        campaign = await create_campaign(
            db,
            name=data['campaign_name'],
            start_parameter=data['campaign_start_parameter'],
            bonus_type='none',
            created_by=db_user.id,
        )
        await state.clear()

        deep_link = await _get_bot_deep_link(callback, campaign.start_parameter)
        texts = get_texts(db_user.language)
        summary = _format_campaign_summary(campaign, texts)
        text = f'✅ <b>Кампания создана!</b>\n\n{summary}\n🔗 Ссылка: <code>{deep_link}</code>'

        await callback.message.edit_text(
            text,
            reply_markup=get_campaign_management_keyboard(campaign.id, campaign.is_active, db_user.language),
        )

    await callback.answer()


@admin_required
@error_handler
async def process_campaign_balance_value(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    try:
        amount_rubles = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer('❌ Введите корректную сумму (например, 100 или 99.5)')
        return

    if amount_rubles <= 0:
        await message.answer('❌ Сумма должна быть больше нуля')
        return

    amount_kopeks = int(round(amount_rubles * 100))
    data = await state.get_data()

    campaign = await create_campaign(
        db,
        name=data['campaign_name'],
        start_parameter=data['campaign_start_parameter'],
        bonus_type='balance',
        balance_bonus_kopeks=amount_kopeks,
        created_by=db_user.id,
    )

    await state.clear()

    deep_link = await _get_bot_deep_link_from_message(message, campaign.start_parameter)
    texts = get_texts(db_user.language)
    summary = _format_campaign_summary(campaign, texts)
    text = f'✅ <b>Кампания создана!</b>\n\n{summary}\n🔗 Ссылка: <code>{deep_link}</code>'

    await message.answer(
        text,
        reply_markup=get_campaign_management_keyboard(campaign.id, campaign.is_active, db_user.language),
    )


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_campaigns_menu, F.data == 'admin_campaigns')
    dp.callback_query.register(show_campaigns_overall_stats, F.data == 'admin_campaigns_stats')
    dp.callback_query.register(show_campaigns_list, F.data == 'admin_campaigns_list')
    dp.callback_query.register(show_campaigns_list, F.data.startswith('admin_campaigns_list_page_'))
    dp.callback_query.register(start_campaign_creation, F.data == 'admin_campaigns_create')
    dp.callback_query.register(show_campaign_stats, F.data.startswith('admin_campaign_stats_'))
    dp.callback_query.register(show_campaign_detail, F.data.startswith('admin_campaign_manage_'))
    dp.callback_query.register(select_campaign_bonus_type, F.data.startswith('campaign_bonus_'))
    dp.message.register(process_campaign_name, AdminStates.creating_campaign_name)
    dp.message.register(process_campaign_start_parameter, AdminStates.creating_campaign_start)
    dp.message.register(process_campaign_balance_value, AdminStates.creating_campaign_balance)
