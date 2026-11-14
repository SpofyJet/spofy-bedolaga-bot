import html
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.server_squad import (
    get_all_server_squads,
    get_server_squad_by_id,
    get_server_squad_by_uuid,
)
from app.database.crud.tariff import get_all_tariffs, get_tariff_by_id
from app.database.crud.user import (
    get_referrals,
    get_user_by_id,
)
from app.database.models import Subscription, SubscriptionStatus, TransactionType, User, UserStatus
from app.keyboards.admin import (
    get_admin_pagination_keyboard,
    get_admin_users_keyboard,
    get_confirmation_keyboard,
    get_user_management_keyboard,
    get_user_restrictions_keyboard,
)
from app.localization.texts import Texts, get_texts
from app.services.remnawave_service import RemnaWaveService
from app.services.subscription_service import SubscriptionService
from app.services.traffic_cycle import begin_traffic_cycle
from app.services.user_service import UserService
from app.states import AdminStates
from app.utils.decorators import admin_required, error_handler
from app.utils.formatters import format_datetime, format_time_ago
from app.utils.formatting import user_html_link
from app.utils.notification_keyboards import keyboard, subscription_button
from app.utils.photo_message import safe_edit_or_resend
from app.utils.subscription_time import format_time_left, local_days_until
from app.utils.user_utils import get_effective_referral_commission_percent


logger = structlog.get_logger(__name__)


# =============================================================================
# Конфигурация фильтров пользователей
# =============================================================================


@dataclass
class UserFilterConfig:
    """Конфигурация для типа фильтра."""

    fsm_state: Any  # State из AdminStates
    title: str
    empty_message: str
    pagination_prefix: str
    order_param: str  # параметр для get_users_page


@admin_required
@error_handler
async def show_users_menu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_service = UserService()
    stats = await user_service.get_user_statistics(db)

    text = f"""
👥 <b>Управление пользователями</b>

📊 <b>Статистика:</b>
• Всего: {stats['total_users']}
• Активных: {stats['active_users']}
• Заблокированных: {stats['blocked_users']}

📈 <b>Новые пользователи:</b>
• Сегодня: {stats['new_today']}
• За неделю: {stats['new_week']}
• За месяц: {stats['new_month']}

Выберите действие:
"""

    await callback.message.edit_text(text, reply_markup=get_admin_users_keyboard(db_user.language))
    await callback.answer()


@admin_required
@error_handler
async def show_users_list(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext, page: int = 1
):
    # Сбрасываем состояние, так как мы в обычном списке
    await state.set_state(None)

    user_service = UserService()
    users_data = await user_service.get_users_page(db, page=page, limit=10)

    if not users_data['users']:
        await callback.message.edit_text(
            '👥 Пользователи не найдены', reply_markup=get_admin_users_keyboard(db_user.language)
        )
        await callback.answer()
        return

    text = f'👥 <b>Список пользователей</b> (стр. {page}/{users_data["total_pages"]})\n\n'
    text += 'Нажмите на пользователя для управления:'

    keyboard = []

    for user in users_data['users']:
        if user.status == UserStatus.ACTIVE.value:
            status_emoji = '✅'
        elif user.status == UserStatus.BLOCKED.value:
            status_emoji = '🚫'
        else:
            status_emoji = '🗑️'

        subscription_emoji = ''
        subs = getattr(user, 'subscriptions', None) or []
        subscription = next((s for s in subs if s.is_active), subs[0] if subs else None)
        if subscription:
            if subscription.is_trial:
                subscription_emoji = '🎁'
            elif subscription.is_active:
                subscription_emoji = '💎'
            else:
                subscription_emoji = '⏰'
        else:
            subscription_emoji = '❌'

        button_text = f'{status_emoji} {subscription_emoji} {user.full_name}'

        if user.balance_kopeks > 0:
            button_text += f' | 💰 {settings.format_price(user.balance_kopeks)}'

        button_text += f' | 📅 {format_time_ago(user.created_at, db_user.language)}'

        if len(button_text) > 60:
            short_name = user.full_name
            if len(short_name) > 20:
                short_name = short_name[:17] + '...'

            button_text = f'{status_emoji} {subscription_emoji} {short_name}'
            if user.balance_kopeks > 0:
                button_text += f' | 💰 {settings.format_price(user.balance_kopeks)}'

        keyboard.append([types.InlineKeyboardButton(text=button_text, callback_data=f'admin_user_manage_{user.id}')])

    if users_data['total_pages'] > 1:
        pagination_row = get_admin_pagination_keyboard(
            users_data['current_page'], users_data['total_pages'], 'admin_users_list', 'admin_users', db_user.language
        ).inline_keyboard[0]
        keyboard.append(pagination_row)

    keyboard.extend(
        [
            [
                types.InlineKeyboardButton(text='🔍 Поиск', callback_data='admin_users_search'),
            ],
            [types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_users')],
        ]
    )

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@admin_required
@error_handler
async def handle_users_list_pagination_fixed(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext
):
    try:
        callback_parts = callback.data.split('_')
        page = int(callback_parts[-1])
        await show_users_list(callback, db_user, db, state, page)
    except (ValueError, IndexError) as e:
        logger.error('Ошибка парсинга номера страницы', error=e)
        await show_users_list(callback, db_user, db, state, 1)


@admin_required
@error_handler
async def start_user_search(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    await callback.message.edit_text(
        '🔍 <b>Поиск пользователя</b>\n\n'
        'Введите для поиска:\n'
        '• Telegram ID\n'
        '• Username (без @)\n'
        '• Имя или фамилию\n\n'
        'Или нажмите /cancel для отмены',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text='❌ Отмена', callback_data='admin_users')]]
        ),
    )

    await state.set_state(AdminStates.waiting_for_user_search)
    await callback.answer()


async def _render_user_subscription_overview(
    callback: types.CallbackQuery, db: AsyncSession, user_id: int, subscription_id: int | None = None
) -> bool:
    user_service = UserService()
    profile = await user_service.get_user_profile(db, user_id)

    if not profile:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return False

    user = profile['user']

    # Multi-tariff: show subscription picker if multiple subscriptions and no explicit choice
    if settings.is_multi_tariff_enabled() and not subscription_id:
        from app.database.crud.subscription import get_active_subscriptions_by_user_id

        all_subs = await get_active_subscriptions_by_user_id(db, user_id)
        await db.refresh(user, ['subscriptions'])
        all_user_subs = getattr(user, 'subscriptions', []) or []
        subs_list = all_user_subs if len(all_user_subs) > len(all_subs) else all_subs

        if len(subs_list) > 1:
            user_link = user_html_link(user)
            user_id_display = user.telegram_id or user.email or f'#{user.id}'
            text = '📱 <b>Выберите подписку для управления</b>\n\n'
            text += f'👤 {user_link} (ID: <code>{user_id_display}</code>)\n\n'
            text += f'У пользователя <b>{len(subs_list)}</b> подписок:\n\n'

            picker_keyboard = []
            for sub in sorted(subs_list, key=lambda s: s.id):
                status_emoji = '✅' if sub.is_active else ('⏸' if sub.status == 'disabled' else '❌')
                tariff_name = ''
                if sub.tariff_id:
                    tariff = await get_tariff_by_id(db, sub.tariff_id)
                    tariff_name = f' • {html.escape(tariff.name)}' if tariff else ''

                days_left = local_days_until(sub.end_date) if sub.end_date else 0
                btn_text = f'{status_emoji} #{sub.id}{tariff_name} ({days_left}д.)'
                picker_keyboard.append(
                    [
                        types.InlineKeyboardButton(
                            text=btn_text,
                            callback_data=f'admin_user_sub_select_{user_id}_{sub.id}',
                        )
                    ]
                )

            picker_keyboard.append(
                [types.InlineKeyboardButton(text='⬅️ К пользователю', callback_data=f'admin_user_manage_{user_id}')]
            )
            await callback.message.edit_text(
                text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=picker_keyboard)
            )
            return True
        if len(subs_list) == 1:
            subscription_id = subs_list[0].id

    # Fetch specific subscription if subscription_id provided
    if subscription_id and settings.is_multi_tariff_enabled():
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = profile['subscription']

    # Suffix routes back to this exact subscription in multi-tariff mode
    _sid = f'_s{subscription.id}' if settings.is_multi_tariff_enabled() and subscription else ''

    text = '📱 <b>Подписка и настройки пользователя</b>\n\n'
    user_link = user_html_link(user)
    user_id_display = user.telegram_id or user.email or f'#{user.id}'
    text += f'👤 {user_link} (ID: <code>{user_id_display}</code>)\n\n'

    keyboard = []

    if subscription:
        status_emoji = '✅' if subscription.is_active else '❌'
        type_emoji = '🎁' if subscription.is_trial else '💎'

        traffic_display = f'{subscription.traffic_used_gb:.1f}/'
        if subscription.traffic_limit_gb == 0:
            traffic_display += '♾️ ГБ'
        else:
            traffic_display += f'{subscription.traffic_limit_gb} ГБ'

        text += f'<b>Статус:</b> {status_emoji} {"Активна" if subscription.is_active else "Неактивна"}\n'
        text += f'<b>Тип:</b> {type_emoji} {"Триал" if subscription.is_trial else "Платная"}\n'

        # Отображение тарифа
        if subscription.tariff_id:
            tariff = await get_tariff_by_id(db, subscription.tariff_id)
            if tariff:
                text += f'<b>Тариф:</b> 📦 {html.escape(tariff.name)}\n'
            else:
                text += f'<b>Тариф:</b> ID {subscription.tariff_id} (удалён)\n'

        text += f'<b>Начало:</b> {format_datetime(subscription.start_date)}\n'
        text += f'<b>Окончание:</b> {format_datetime(subscription.end_date)}\n'
        text += f'<b>Трафик:</b> {traffic_display}\n'
        text += f'<b>Устройства:</b> {Texts.format_device_limit(subscription.device_limit)}\n'

        if subscription.is_active:
            text += f'<b>Осталось:</b> {format_time_left(None, subscription.end_date)}\n'

        current_squads = subscription.connected_squads or []
        if current_squads:
            text += '\n<b>Подключенные серверы:</b>\n'
            for squad_uuid in current_squads:
                try:
                    server = await get_server_squad_by_uuid(db, squad_uuid)
                    if server:
                        text += f'• {html.escape(server.display_name)}\n'
                    else:
                        text += f'• {squad_uuid[:8]}... (неизвестный)\n'
                except Exception as e:
                    logger.error('Ошибка получения сервера', squad_uuid=squad_uuid, error=e)
                    text += f'• {squad_uuid[:8]}... (ошибка загрузки)\n'
        else:
            text += '\n<b>Подключенные серверы:</b> отсутствуют\n'

        keyboard = [
            [
                types.InlineKeyboardButton(text='⏰ Продлить', callback_data=f'admin_sub_extend_{user_id}{_sid}'),
                types.InlineKeyboardButton(text='💳 Купить подписку', callback_data=f'admin_sub_buy_{user_id}{_sid}'),
            ],
            [
                types.InlineKeyboardButton(
                    text='🔄 Тип подписки', callback_data=f'admin_sub_change_type_{user_id}{_sid}'
                ),
                types.InlineKeyboardButton(
                    text='📊 Добавить трафик', callback_data=f'admin_sub_traffic_{user_id}{_sid}'
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text='🌍 Сменить сервер', callback_data=f'admin_user_change_server_{user_id}{_sid}'
                ),
            ],
        ]

        # Кнопки тарифов в режиме тарифов
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text='📦 Сменить тариф', callback_data=f'admin_sub_change_tariff_{user_id}{_sid}'
                ),
            ]
        )

        if subscription.is_active:
            keyboard.append(
                [
                    types.InlineKeyboardButton(
                        text='🚫 Деактивировать', callback_data=f'admin_sub_deactivate_{user_id}{_sid}'
                    )
                ]
            )
        else:
            keyboard.append(
                [
                    types.InlineKeyboardButton(
                        text='✅ Активировать', callback_data=f'admin_sub_activate_{user_id}{_sid}'
                    ),
                ]
            )

        # Обнулить подписку «как будто не оформляли»: сбросить наспамленные дни и доступ,
        # отключить в панели — но СОХРАНИТЬ пользователя и его тикеты (в отличие от удаления).
        keyboard.append(
            [types.InlineKeyboardButton(text='🧹 Обнулить подписку', callback_data=f'admin_sub_reset_{user_id}{_sid}')]
        )
    else:
        text += '❌ <b>Подписка отсутствует</b>\n\n'
        text += 'Пользователь еще не активировал подписку.'

        keyboard = [
            [
                types.InlineKeyboardButton(text='💎 Выдать подписку', callback_data=f'admin_sub_grant_{user_id}'),
            ]
        ]

    keyboard.append([types.InlineKeyboardButton(text='⬅️ К пользователю', callback_data=f'admin_user_manage_{user_id}')])

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    return True


def _extract_admin_sub_context(callback_data: str) -> tuple[int, int | None]:
    """Extract user_id and optional subscription_id from admin callback_data.

    Patterns:
    - 'admin_sub_extend_123'       -> (123, None)
    - 'admin_sub_extend_123_s456'  -> (123, 456)
    """
    parts = callback_data.split('_')
    subscription_id = None
    if parts[-1].startswith('s') and parts[-1][1:].isdigit():
        subscription_id = int(parts[-1][1:])
        user_id = int(parts[-2])
    else:
        user_id = int(parts[-1])
    return user_id, subscription_id


@admin_required
@error_handler
async def show_user_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id = int(callback.data.split('_')[-1])

    if await _render_user_subscription_overview(callback, db, user_id):
        await callback.answer()


@admin_required
@error_handler
async def admin_select_user_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Handle subscription picker selection in multi-tariff mode."""
    parts = callback.data.split('_')
    user_id = int(parts[-2])
    subscription_id = int(parts[-1])

    if await _render_user_subscription_overview(callback, db, user_id, subscription_id=subscription_id):
        await callback.answer()


@admin_required
@error_handler
async def show_user_transactions(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id = int(callback.data.split('_')[-1])

    from app.database.crud.transaction import get_user_transactions

    user = await get_user_by_id(db, user_id)
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    transactions = await get_user_transactions(db, user_id, limit=10)

    text = '💳 <b>Транзакции пользователя</b>\n\n'
    user_link = user_html_link(user)
    user_id_display = user.telegram_id or user.email or f'#{user.id}'
    text += f'👤 {user_link} (ID: <code>{user_id_display}</code>)\n'
    text += f'💰 Текущий баланс: {settings.format_price(user.balance_kopeks)}\n\n'

    if transactions:
        text += '<b>Последние транзакции:</b>\n\n'

        for transaction in transactions:
            type_emoji = '📈' if transaction.amount_kopeks > 0 else '📉'
            text += f'{type_emoji} {settings.format_price(abs(transaction.amount_kopeks))}\n'
            text += f'📋 {html.escape(transaction.description or "")}\n'
            text += f'📅 {format_datetime(transaction.created_at)}\n\n'
    else:
        text += '📭 <b>Транзакции отсутствуют</b>'

    await callback.message.edit_text(
        text,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text='⬅️ К пользователю', callback_data=f'admin_user_manage_{user_id}')]
            ]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def confirm_user_delete(callback: types.CallbackQuery, db_user: User):
    user_id = int(callback.data.split('_')[-1])

    await callback.message.edit_text(
        '🗑️ <b>Удаление пользователя</b>\n\n'
        '⚠️ <b>ВНИМАНИЕ!</b>\n'
        'Вы уверены, что хотите удалить этого пользователя?\n\n'
        'Это действие:\n'
        '• Пометит пользователя как удаленного\n'
        '• Деактивирует его подписку\n'
        '• Заблокирует доступ к боту\n\n'
        'Данное действие необратимо!',
        reply_markup=get_confirmation_keyboard(
            f'admin_user_delete_confirm_{user_id}', f'admin_user_manage_{user_id}', db_user.language
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def delete_user_account(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id = int(callback.data.split('_')[-1])

    user_service = UserService()
    delete_result = await user_service.delete_user_account(db, user_id, db_user.id, force_panel_delete=True)

    if delete_result.bot_deleted:
        await callback.message.edit_text(
            '✅ Пользователь успешно удален',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👥 К списку пользователей', callback_data='admin_users_list')]
                ]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка удаления пользователя',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👤 К пользователю', callback_data=f'admin_user_manage_{user_id}')]
                ]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def process_user_search(message: types.Message, db_user: User, state: FSMContext, db: AsyncSession):
    query = message.text.strip()

    if not query:
        await message.answer('❌ Введите корректный запрос для поиска')
        return

    user_service = UserService()
    search_results = await user_service.search_users(db, query, page=1, limit=10)

    if not search_results['users']:
        await message.answer(
            f"🔍 По запросу '<b>{html.escape(query)}</b>' ничего не найдено",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_users')]]
            ),
        )
        await state.clear()
        return

    text = f"🔍 <b>Результаты поиска:</b> '{html.escape(query)}'\n\n"
    text += 'Выберите пользователя:'

    keyboard = []

    for user in search_results['users']:
        if user.status == UserStatus.ACTIVE.value:
            status_emoji = '✅'
        elif user.status == UserStatus.BLOCKED.value:
            status_emoji = '🚫'
        else:
            status_emoji = '🗑️'

        subscription_emoji = ''
        subs = getattr(user, 'subscriptions', None) or []
        subscription = next((s for s in subs if s.is_active), subs[0] if subs else None)
        if subscription:
            if subscription.is_trial:
                subscription_emoji = '🎁'
            elif subscription.is_active:
                subscription_emoji = '💎'
            else:
                subscription_emoji = '⏰'
        else:
            subscription_emoji = '❌'

        button_text = f'{status_emoji} {subscription_emoji} {user.full_name}'

        user_id_display = user.telegram_id or user.email or f'#{user.id}'
        button_text += f' | 🆔 {user_id_display}'

        if user.balance_kopeks > 0:
            button_text += f' | 💰 {settings.format_price(user.balance_kopeks)}'

        if len(button_text) > 60:
            short_name = user.full_name
            if len(short_name) > 15:
                short_name = short_name[:12] + '...'
            button_text = f'{status_emoji} {subscription_emoji} {short_name} | 🆔 {user_id_display}'

        keyboard.append([types.InlineKeyboardButton(text=button_text, callback_data=f'admin_user_manage_{user.id}')])

    keyboard.append([types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_users')])

    await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.clear()


@admin_required
@error_handler
async def show_user_management(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    # Поддерживаем переход "из тикета": admin_user_manage_{userId}_from_ticket_{ticketId}
    parts = callback.data.split('_')
    try:
        user_id = int(parts[3])  # admin_user_manage_{userId}
    except Exception:
        user_id = int(callback.data.split('_')[-1])
    origin_ticket_id = None
    if 'from' in parts and 'ticket' in parts:
        try:
            origin_ticket_id = int(parts[-1])
        except Exception:
            origin_ticket_id = None
    # Если пришли из тикета — запомним в состоянии, чтобы сохранять кнопку возврата
    try:
        if origin_ticket_id:
            await state.update_data(origin_ticket_id=origin_ticket_id, origin_ticket_user_id=user_id)
    except Exception:
        logger.debug('Ignored error in show_user_management', exc_info=True)
    # Если не пришло в колбэке — попробуем достать из состояния
    if origin_ticket_id is None:
        try:
            data_state = await state.get_data()
            if data_state.get('origin_ticket_user_id') == user_id:
                origin_ticket_id = data_state.get('origin_ticket_id')
        except Exception:
            logger.debug('Ignored error in show_user_management', exc_info=True)

    # Проверяем, откуда пришел пользователь
    back_callback = 'admin_users_list'

    # Если callback_data содержит информацию о том, что мы пришли из списка по балансу
    # В реальности это сложно определить, поэтому будем использовать состояние

    user_service = UserService()
    profile = await user_service.get_user_profile(db, user_id)

    if not profile:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    user = profile['user']
    subscription = profile['subscription']

    texts = get_texts(db_user.language)

    status_map = {
        UserStatus.ACTIVE.value: texts.ADMIN_USER_STATUS_ACTIVE,
        UserStatus.BLOCKED.value: texts.ADMIN_USER_STATUS_BLOCKED,
        UserStatus.DELETED.value: texts.ADMIN_USER_STATUS_DELETED,
    }
    status_text = status_map.get(user.status, texts.ADMIN_USER_STATUS_UNKNOWN)

    username_display = f'@{user.username}' if user.username else texts.ADMIN_USER_USERNAME_NOT_SET
    last_activity = (
        format_time_ago(user.last_activity, db_user.language)
        if user.last_activity
        else texts.ADMIN_USER_LAST_ACTIVITY_UNKNOWN
    )

    sections = [
        texts.ADMIN_USER_MANAGEMENT_PROFILE.format(
            name=html.escape(user.full_name),
            telegram_id=user.telegram_id,
            username=username_display,
            status=status_text,
            language=user.language,
            balance=settings.format_price(user.balance_kopeks),
            transactions=profile['transactions_count'],
            registration=format_datetime(user.created_at),
            last_activity=last_activity,
            registration_days=profile['registration_days'],
        )
    ]

    if subscription:
        subscription_type = (
            texts.ADMIN_USER_SUBSCRIPTION_TYPE_TRIAL
            if subscription.is_trial
            else texts.ADMIN_USER_SUBSCRIPTION_TYPE_PAID
        )
        subscription_status = (
            texts.ADMIN_USER_SUBSCRIPTION_STATUS_ACTIVE
            if subscription.is_active
            else texts.ADMIN_USER_SUBSCRIPTION_STATUS_INACTIVE
        )
        traffic_usage = texts.ADMIN_USER_TRAFFIC_USAGE.format(
            used=f'{subscription.traffic_used_gb:.1f}',
            limit=subscription.traffic_limit_gb,
        )
        sections.append(
            texts.ADMIN_USER_MANAGEMENT_SUBSCRIPTION.format(
                type=subscription_type,
                status=subscription_status,
                end_date=format_datetime(subscription.end_date),
                traffic=traffic_usage,
                devices=Texts.format_device_limit(subscription.device_limit),
                countries=len(subscription.connected_squads or []),
            )
        )
    else:
        sections.append(texts.ADMIN_USER_MANAGEMENT_SUBSCRIPTION_NONE)

    # Display promo groups
    primary_group = user.get_primary_promo_group()
    if primary_group:
        sections.append(
            texts.t(
                'ADMIN_USER_PROMO_GROUPS_PRIMARY',
                '⭐ Основная: {name} (Priority: {priority})',
            ).format(name=html.escape(primary_group.name), priority=getattr(primary_group, 'priority', 0))
        )
        sections.append(
            texts.ADMIN_USER_MANAGEMENT_PROMO_GROUP.format(
                name=html.escape(primary_group.name),
                server_discount=primary_group.server_discount_percent,
                traffic_discount=primary_group.traffic_discount_percent,
                device_discount=primary_group.device_discount_percent,
            )
        )

        # Show additional groups if any
        if user.user_promo_groups and len(user.user_promo_groups) > 1:
            additional_groups = [
                upg.promo_group
                for upg in user.user_promo_groups
                if upg.promo_group and upg.promo_group.id != primary_group.id
            ]
            if additional_groups:
                sections.append(
                    texts.t(
                        'ADMIN_USER_PROMO_GROUPS_ADDITIONAL',
                        'Дополнительные группы:',
                    )
                )
                for group in additional_groups:
                    sections.append(f'  • {html.escape(group.name)} (Priority: {getattr(group, "priority", 0)})')
    else:
        sections.append(texts.ADMIN_USER_MANAGEMENT_PROMO_GROUP_NONE)

    # Показать ограничения пользователя если есть
    restriction_topup = getattr(user, 'restriction_topup', False)
    restriction_subscription = getattr(user, 'restriction_subscription', False)
    if restriction_topup or restriction_subscription:
        restriction_lines = ['⚠️ <b>Ограничения:</b>']
        if restriction_topup:
            restriction_lines.append('  • 🚫 Пополнение запрещено')
        if restriction_subscription:
            restriction_lines.append('  • 🚫 Продление/покупка запрещена')
        restriction_reason = getattr(user, 'restriction_reason', None)
        if restriction_reason:
            restriction_lines.append(f'  📝 Причина: {html.escape(restriction_reason)}')
        sections.append('\n'.join(restriction_lines))

    text = '\n\n'.join(sections)

    # Проверяем состояние, чтобы определить, откуда пришел пользователь
    current_state = await state.get_state()
    if current_state == AdminStates.viewing_user_from_balance_list:
        back_callback = 'admin_users_balance_filter'
    elif current_state == AdminStates.viewing_user_from_campaign_list:
        back_callback = 'admin_users_campaign_filter'
    elif current_state == AdminStates.viewing_user_from_ready_to_renew_list:
        back_callback = 'admin_users_ready_to_renew_filter'
    elif current_state == AdminStates.viewing_user_from_potential_customers_list:
        back_callback = 'admin_users_potential_customers_filter'

    # Базовая клавиатура профиля
    kb = get_user_management_keyboard(user.id, user.status, db_user.language, back_callback)
    # Если пришли из тикета — добавим в начало кнопку возврата к тикету
    try:
        if origin_ticket_id:
            back_to_ticket_btn = types.InlineKeyboardButton(
                text='🎫 Вернуться к тикету', callback_data=f'admin_view_ticket_{origin_ticket_id}'
            )
            kb.inline_keyboard.insert(0, [back_to_ticket_btn])
    except Exception:
        logger.debug('Ignored error in show_user_management', exc_info=True)

    message = callback.message
    if not isinstance(message, types.Message):
        # None или InaccessibleMessage (например, уведомление старше 48ч) — редактировать нельзя
        texts = get_texts(db_user.language)
        await callback.answer(
            texts.t('MESSAGE_TOO_OLD', '⚠️ Сообщение устарело. Откройте обращение заново.'), show_alert=True
        )
        return
    await safe_edit_or_resend(message, text, kb)
    await callback.answer()


async def _build_user_referrals_view(
    db: AsyncSession,
    language: str,
    user_id: int,
    limit: int = 30,
) -> tuple[str, InlineKeyboardMarkup] | None:
    texts = get_texts(language)

    user = await get_user_by_id(db, user_id)
    if not user:
        return None

    referrals = await get_referrals(db, user_id)

    effective_percent = get_effective_referral_commission_percent(user)
    default_percent = settings.REFERRAL_COMMISSION_PERCENT

    header = texts.t(
        'ADMIN_USER_REFERRALS_TITLE',
        '🤝 <b>Рефералы пользователя</b>',
    )
    summary = texts.t(
        'ADMIN_USER_REFERRALS_SUMMARY',
        '👤 {name} (ID: <code>{telegram_id}</code>)\n👥 Всего рефералов: {count}',
    ).format(
        name=html.escape(user.full_name),
        telegram_id=user.telegram_id,
        count=len(referrals),
    )

    lines: list[str] = [header, summary]

    if user.referral_commission_percent is None and settings.is_referral_levels_scheme():
        # В многоуровневой схеме «стандартный процент» не существует: у каждого
        # уровня свой, а пустой означает ноль. Печатать REFERRAL_COMMISSION_PERCENT
        # значит называть админу ставку, по которой ничего не начисляется.
        lines.append(
            texts.t(
                'ADMIN_USER_REFERRAL_COMMISSION_LEVELS',
                '• Процент комиссии: по уровням реферальной схемы',
            )
        )
    elif user.referral_commission_percent is None:
        lines.append(
            texts.t(
                'ADMIN_USER_REFERRAL_COMMISSION_DEFAULT',
                '• Процент комиссии: {percent}% (стандартное значение)',
            ).format(percent=effective_percent)
        )
    else:
        lines.append(
            texts.t(
                'ADMIN_USER_REFERRAL_COMMISSION_CUSTOM',
                '• Индивидуальный процент: {percent}% (стандарт: {default_percent}%)',
            ).format(
                percent=user.referral_commission_percent,
                default_percent=default_percent,
            )
        )

    if referrals:
        lines.append(
            texts.t(
                'ADMIN_USER_REFERRALS_LIST_HEADER',
                '<b>Список рефералов:</b>',
            )
        )
        items = []
        for referral in referrals[:limit]:
            username_part = f', @{referral.username}' if referral.username else ''
            safe_name = html.escape(referral.full_name)
            if referral.telegram_id:
                referral_link = f'<a href="tg://user?id={referral.telegram_id}">{safe_name}</a>'
                referral_id_display = referral.telegram_id
            else:
                referral_link = f'<b>{safe_name}</b>'
                referral_id_display = referral.email or f'#{referral.id}'
            items.append(
                texts.t(
                    'ADMIN_USER_REFERRALS_LIST_ITEM',
                    '• {name} (ID: <code>{telegram_id}</code>{username_part})',
                ).format(
                    name=referral_link,
                    telegram_id=referral_id_display,
                    username_part=username_part,
                )
            )

        lines.append('\n'.join(items))

        if len(referrals) > limit:
            remaining = len(referrals) - limit
            lines.append(
                texts.t(
                    'ADMIN_USER_REFERRALS_LIST_TRUNCATED',
                    '• … и ещё {count} рефералов',
                ).format(count=remaining)
            )
    else:
        lines.append(
            texts.t(
                'ADMIN_USER_REFERRALS_EMPTY',
                'Рефералов пока нет.',
            )
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BACK,
                    callback_data=f'admin_user_manage_{user_id}',
                )
            ],
        ]
    )

    return '\n\n'.join(lines), keyboard


@admin_required
@error_handler
async def show_user_referrals(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    user_id = int(callback.data.split('_')[-1])

    current_state = await state.get_state()
    if current_state in {AdminStates.editing_user_referrals, AdminStates.editing_user_referral_percent}:
        data = await state.get_data()
        preserved_data = {
            key: value
            for key, value in data.items()
            if key not in {'editing_referrals_user_id', 'referrals_message_id', 'editing_referral_percent_user_id'}
        }
        await state.clear()
        if preserved_data:
            await state.update_data(**preserved_data)

    view = await _build_user_referrals_view(db, db_user.language, user_id)
    if not view:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    text, keyboard = view

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
    )
    await callback.answer()


@admin_required
@error_handler
async def start_balance_edit(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    user_id = int(callback.data.split('_')[-1])

    await state.update_data(editing_user_id=user_id)

    await callback.message.edit_text(
        '💰 <b>Изменение баланса</b>\n\n'
        'Введите сумму для изменения баланса:\n'
        '• Положительное число для пополнения\n'
        '• Отрицательное число для списания\n'
        '• Примеры: 100, -50, 25.5\n\n'
        'Или нажмите /cancel для отмены',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text='❌ Отмена', callback_data=f'admin_user_manage_{user_id}')]
            ]
        ),
    )

    await state.set_state(AdminStates.editing_user_balance)
    await callback.answer()


@admin_required
@error_handler
async def process_balance_edit(message: types.Message, db_user: User, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    user_id = data.get('editing_user_id')

    if not user_id:
        await message.answer('❌ Ошибка: пользователь не найден')
        await state.clear()
        return

    try:
        amount_rubles = float(message.text.replace(',', '.'))
        amount_kopeks = settings.rubles_to_kopeks(amount_rubles)

        if abs(amount_kopeks) > 10000000:
            await message.answer('❌ Слишком большая сумма (максимум 100,000 ₽)')
            return

        user_service = UserService()

        description = f'Изменение баланса администратором {db_user.full_name}'
        if amount_kopeks > 0:
            description = f'Пополнение администратором: +{int(amount_rubles)} ₽'
        else:
            description = f'Списание администратором: {int(amount_rubles)} ₽'

        success = await user_service.update_user_balance(
            db, user_id, amount_kopeks, description, db_user.id, bot=message.bot, admin_name=db_user.full_name
        )

        if success:
            action = 'пополнен' if amount_kopeks > 0 else 'списан'
            await message.answer(
                f'✅ Баланс пользователя {action} на {settings.format_price(abs(amount_kopeks))}',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(
                                text='👤 К пользователю', callback_data=f'admin_user_manage_{user_id}'
                            )
                        ]
                    ]
                ),
            )
        else:
            await message.answer('❌ Ошибка изменения баланса (возможно, недостаточно средств для списания)')

    except ValueError:
        await message.answer('❌ Введите корректную сумму (например: 100 или -50)')
        return

    await state.clear()


@admin_required
@error_handler
async def confirm_user_block(callback: types.CallbackQuery, db_user: User):
    user_id = int(callback.data.split('_')[-1])

    await callback.message.edit_text(
        '🚫 <b>Блокировка пользователя</b>\n\n'
        'Вы уверены, что хотите заблокировать этого пользователя?\n'
        'Пользователь потеряет доступ к боту.',
        reply_markup=get_confirmation_keyboard(
            f'admin_user_block_confirm_{user_id}', f'admin_user_manage_{user_id}', db_user.language
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def block_user(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id = int(callback.data.split('_')[-1])

    user_service = UserService()
    success = await user_service.block_user(db, user_id, db_user.id, 'Заблокирован администратором')

    if success:
        await callback.message.edit_text(
            '✅ Пользователь заблокирован',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👤 К пользователю', callback_data=f'admin_user_manage_{user_id}')]
                ]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка блокировки пользователя',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👤 К пользователю', callback_data=f'admin_user_manage_{user_id}')]
                ]
            ),
        )

    await callback.answer()


# ============ УПРАВЛЕНИЕ ОГРАНИЧЕНИЯМИ ПОЛЬЗОВАТЕЛЯ ============


@admin_required
@error_handler
async def show_user_restrictions(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Показать меню управления ограничениями пользователя."""
    user_id = int(callback.data.split('_')[-1])
    user = await get_user_by_id(db, user_id)

    if not user:
        await callback.answer('Пользователь не найден', show_alert=True)
        return

    get_texts(db_user.language)

    # Формируем текст с информацией об ограничениях
    restriction_topup = user.restriction_topup
    restriction_subscription = user.restriction_subscription
    restriction_reason = user.restriction_reason

    text_lines = [
        '⚠️ <b>Ограничения пользователя</b>',
        f'👤 {html.escape(user.full_name)}',
        '',
        '✅ — разрешено, 🚫 — запрещено',
        '',
        f'{"🚫" if restriction_topup else "✅"} Пополнение баланса',
        f'{"🚫" if restriction_subscription else "✅"} Продление/покупка подписки',
    ]

    if restriction_reason:
        text_lines.append('')
        text_lines.append(f'📝 <b>Причина:</b> {html.escape(restriction_reason)}')

    keyboard = get_user_restrictions_keyboard(
        user_id=user_id,
        restriction_topup=restriction_topup,
        restriction_subscription=restriction_subscription,
        language=db_user.language,
    )

    await callback.message.edit_text('\n'.join(text_lines), reply_markup=keyboard)
    await callback.answer()


@admin_required
@error_handler
async def toggle_user_restriction_topup(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Переключить ограничение на пополнение баланса."""
    user_id = int(callback.data.split('_')[-1])
    user = await get_user_by_id(db, user_id)

    if not user:
        await callback.answer('Пользователь не найден', show_alert=True)
        return

    # Переключаем ограничение
    current_value = user.restriction_topup
    user.restriction_topup = not current_value
    await db.commit()

    action = 'установлено' if user.restriction_topup else 'снято'
    await callback.answer(f'Ограничение на пополнение {action}', show_alert=False)

    # Обновляем меню
    await show_user_restrictions(callback, db_user, db)


@admin_required
@error_handler
async def toggle_user_restriction_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Переключить ограничение на продление/покупку подписки."""
    user_id = int(callback.data.split('_')[-1])
    user = await get_user_by_id(db, user_id)

    if not user:
        await callback.answer('Пользователь не найден', show_alert=True)
        return

    # Переключаем ограничение
    current_value = user.restriction_subscription
    user.restriction_subscription = not current_value
    await db.commit()

    action = 'установлено' if user.restriction_subscription else 'снято'
    await callback.answer(f'Ограничение на подписку {action}', show_alert=False)

    # Обновляем меню
    await show_user_restrictions(callback, db_user, db)


@admin_required
@error_handler
async def ask_restriction_reason(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    """Запросить ввод причины ограничения."""
    user_id = int(callback.data.split('_')[-1])
    user = await get_user_by_id(db, user_id)

    if not user:
        await callback.answer('Пользователь не найден', show_alert=True)
        return

    current_reason = user.restriction_reason or ''

    await state.set_state(AdminStates.editing_user_restriction_reason)
    await state.update_data(restriction_user_id=user_id)

    text = (
        '📝 <b>Введите причину ограничения</b>\n\n'
        'Эта причина будет показана пользователю при попытке '
        'выполнить запрещённое действие.\n\n'
    )
    if current_reason:
        text += f'Текущая причина: <i>{html.escape(current_reason)}</i>\n\n'
    text += 'Отправьте новую причину или /cancel для отмены:'

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='❌ Отмена', callback_data=f'admin_user_restrictions_{user_id}')]
            ]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def save_restriction_reason(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    """Сохранить причину ограничения."""
    data = await state.get_data()
    user_id = data.get('restriction_user_id')

    if not user_id:
        await message.answer('Ошибка: пользователь не найден')
        await state.clear()
        return

    user = await get_user_by_id(db, user_id)
    if not user:
        await message.answer('Ошибка: пользователь не найден')
        await state.clear()
        return

    reason = message.text.strip()[:500]  # Ограничение 500 символов
    user.restriction_reason = reason
    await db.commit()

    await state.clear()

    # Формируем текст с обновлённой информацией
    restriction_topup = user.restriction_topup
    restriction_subscription = user.restriction_subscription

    text_lines = [
        '✅ <b>Причина ограничения сохранена</b>',
        '',
        '⚠️ <b>Ограничения пользователя</b>',
        f'👤 {html.escape(user.full_name)}',
        '',
        f'{"🚫" if restriction_topup else "✅"} Пополнение баланса',
        f'{"🚫" if restriction_subscription else "✅"} Продление/покупка подписки',
        '',
        f'📝 <b>Причина:</b> {html.escape(reason)}',
    ]

    keyboard = get_user_restrictions_keyboard(
        user_id=user_id,
        restriction_topup=restriction_topup,
        restriction_subscription=restriction_subscription,
        language=db_user.language,
    )

    await message.answer('\n'.join(text_lines), reply_markup=keyboard)


@admin_required
@error_handler
async def clear_user_restrictions(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Снять все ограничения с пользователя."""
    user_id = int(callback.data.split('_')[-1])
    user = await get_user_by_id(db, user_id)

    if not user:
        await callback.answer('Пользователь не найден', show_alert=True)
        return

    # Снимаем все ограничения
    user.restriction_topup = False
    user.restriction_subscription = False
    user.restriction_reason = None
    await db.commit()

    await callback.answer('Все ограничения сняты', show_alert=True)

    # Обновляем меню
    await show_user_restrictions(callback, db_user, db)


@admin_required
@error_handler
async def confirm_user_unblock(callback: types.CallbackQuery, db_user: User):
    user_id = int(callback.data.split('_')[-1])

    await callback.message.edit_text(
        '✅ <b>Разблокировка пользователя</b>\n\n'
        'Вы уверены, что хотите разблокировать этого пользователя?\n'
        'Пользователь снова получит доступ к боту.',
        reply_markup=get_confirmation_keyboard(
            f'admin_user_unblock_confirm_{user_id}', f'admin_user_manage_{user_id}', db_user.language
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def unblock_user(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id = int(callback.data.split('_')[-1])

    user_service = UserService()
    success = await user_service.unblock_user(db, user_id, db_user.id)

    if success:
        await callback.message.edit_text(
            '✅ Пользователь разблокирован',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👤 К пользователю', callback_data=f'admin_user_manage_{user_id}')]
                ]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка разблокировки пользователя',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👤 К пользователю', callback_data=f'admin_user_manage_{user_id}')]
                ]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def extend_user_subscription(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    await state.update_data(extending_user_id=user_id, admin_subscription_id=subscription_id)

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    await callback.message.edit_text(
        '⏰ <b>Продление подписки</b>\n\n'
        'Введите количество дней для изменения:\n'
        '• Положительные значения продлят подписку\n'
        '• Отрицательные сократят срок подписки\n'
        '• Диапазон: от -365 до 365 дней (0 недопустимо)\n\n'
        'Или нажмите /cancel для отмены',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text='-7 дней', callback_data=f'admin_sub_extend_days_{user_id}{_sid}_-7'
                    ),
                    types.InlineKeyboardButton(
                        text='-30 дней', callback_data=f'admin_sub_extend_days_{user_id}{_sid}_-30'
                    ),
                ],
                [
                    types.InlineKeyboardButton(text='7 дней', callback_data=f'admin_sub_extend_days_{user_id}{_sid}_7'),
                    types.InlineKeyboardButton(
                        text='30 дней', callback_data=f'admin_sub_extend_days_{user_id}{_sid}_30'
                    ),
                ],
                [
                    types.InlineKeyboardButton(
                        text='90 дней', callback_data=f'admin_sub_extend_days_{user_id}{_sid}_90'
                    ),
                    types.InlineKeyboardButton(
                        text='180 дней', callback_data=f'admin_sub_extend_days_{user_id}{_sid}_180'
                    ),
                ],
                [types.InlineKeyboardButton(text='❌ Отмена', callback_data=back_cb)],
            ]
        ),
    )

    await state.set_state(AdminStates.extending_subscription)
    await callback.answer()


@admin_required
@error_handler
async def process_subscription_extension_days(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    parts = callback.data.split('_')
    # days is always the last part (may be negative, e.g. '-7')
    days = int(parts[-1])
    # Check if second-to-last part is a subscription_id marker (e.g. 's456')
    if parts[-2].startswith('s') and parts[-2][1:].isdigit():
        subscription_id = int(parts[-2][1:])
        user_id = int(parts[-3])
    else:
        subscription_id = None
        user_id = int(parts[-2])

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    if days == 0 or days < -365 or days > 365:
        await callback.answer('❌ Количество дней должно быть от -365 до 365, исключая 0', show_alert=True)
        return

    success = await _extend_subscription_by_days(db, user_id, days, db_user.id, subscription_id=subscription_id)

    if success:
        if days > 0:
            action_text = f'продлена на {days} дней'
        else:
            action_text = f'уменьшена на {abs(days)} дней'
        await callback.message.edit_text(
            f'✅ Подписка пользователя {action_text}',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка продления подписки',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def process_subscription_extension_text(
    message: types.Message, db_user: User, state: FSMContext, db: AsyncSession
):
    data = await state.get_data()
    user_id = data.get('extending_user_id')
    subscription_id = data.get('admin_subscription_id')

    if not user_id:
        await message.answer('❌ Ошибка: пользователь не найден')
        await state.clear()
        return

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    try:
        days = int(message.text.strip())

        if days == 0 or days < -365 or days > 365:
            await message.answer('❌ Количество дней должно быть от -365 до 365, исключая 0')
            return

        success = await _extend_subscription_by_days(db, user_id, days, db_user.id, subscription_id=subscription_id)

        if success:
            if days > 0:
                action_text = f'продлена на {days} дней'
            else:
                action_text = f'уменьшена на {abs(days)} дней'
            await message.answer(
                f'✅ Подписка пользователя {action_text}',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
                ),
            )
        else:
            await message.answer('❌ Ошибка продления подписки')

    except ValueError:
        await message.answer('❌ Введите корректное число дней')
        return

    await state.clear()


@admin_required
@error_handler
async def add_subscription_traffic(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    await state.update_data(traffic_user_id=user_id, admin_subscription_id=subscription_id)

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    await callback.message.edit_text(
        '📊 <b>Добавление трафика</b>\n\n'
        'Введите количество ГБ для добавления:\n'
        '• Например: 50, 100, 500\n'
        '• Максимум: 10000 ГБ\n\n'
        'Или нажмите /cancel для отмены',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text='50 ГБ', callback_data=f'admin_sub_traffic_add_{user_id}{_sid}_50'),
                    types.InlineKeyboardButton(
                        text='100 ГБ', callback_data=f'admin_sub_traffic_add_{user_id}{_sid}_100'
                    ),
                ],
                [
                    types.InlineKeyboardButton(
                        text='500 ГБ', callback_data=f'admin_sub_traffic_add_{user_id}{_sid}_500'
                    ),
                    types.InlineKeyboardButton(
                        text='1000 ГБ', callback_data=f'admin_sub_traffic_add_{user_id}{_sid}_1000'
                    ),
                ],
                [
                    types.InlineKeyboardButton(
                        text='♾️ Безлимит', callback_data=f'admin_sub_traffic_add_{user_id}{_sid}_0'
                    ),
                ],
                [types.InlineKeyboardButton(text='❌ Отмена', callback_data=back_cb)],
            ]
        ),
    )

    await state.set_state(AdminStates.adding_traffic)
    await callback.answer()


@admin_required
@error_handler
async def process_traffic_addition_button(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    parts = callback.data.split('_')
    gb = int(parts[-1])
    if parts[-2].startswith('s') and parts[-2][1:].isdigit():
        subscription_id = int(parts[-2][1:])
        user_id = int(parts[-3])
    else:
        subscription_id = None
        user_id = int(parts[-2])

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    success = await _add_subscription_traffic(db, user_id, gb, db_user.id, subscription_id=subscription_id)

    if success:
        traffic_text = '♾️ безлимитный' if gb == 0 else f'{gb} ГБ'
        await callback.message.edit_text(
            f'✅ К подписке пользователя добавлен трафик: {traffic_text}',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка добавления трафика',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def process_traffic_addition_text(message: types.Message, db_user: User, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    user_id = data.get('traffic_user_id')
    subscription_id = data.get('admin_subscription_id')

    if not user_id:
        await message.answer('❌ Ошибка: пользователь не найден')
        await state.clear()
        return

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    try:
        gb = int(message.text.strip())

        if gb < 0 or gb > 10000:
            await message.answer('❌ Количество ГБ должно быть от 0 до 10000 (0 = безлимит)')
            return

        success = await _add_subscription_traffic(db, user_id, gb, db_user.id, subscription_id=subscription_id)

        if success:
            traffic_text = '♾️ безлимитный' if gb == 0 else f'{gb} ГБ'
            await message.answer(
                f'✅ К подписке пользователя добавлен трафик: {traffic_text}',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
                ),
            )
        else:
            await message.answer('❌ Ошибка добавления трафика')

    except ValueError:
        await message.answer('❌ Введите корректное число ГБ')
        return

    await state.clear()


@admin_required
@error_handler
async def deactivate_user_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    await callback.message.edit_text(
        '🚫 <b>Деактивация подписки</b>\n\n'
        'Вы уверены, что хотите деактивировать подписку этого пользователя?\n'
        'Пользователь потеряет доступ к сервису.',
        reply_markup=get_confirmation_keyboard(
            f'admin_sub_deactivate_confirm_{user_id}{_sid}', back_cb, db_user.language
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def confirm_subscription_deactivation(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    success = await _deactivate_user_subscription(db, user_id, db_user.id, subscription_id=subscription_id)

    if success:
        await callback.message.edit_text(
            '✅ Подписка пользователя деактивирована',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка деактивации подписки',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def reset_user_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Подтверждение полного обнуления подписки (с сохранением пользователя и тикетов)."""
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    await callback.message.edit_text(
        '🧹 <b>Обнуление подписки</b>\n\n'
        'Подписка будет полностью обнулена «как будто пользователь её не оформлял»:\n'
        '• срок и наспамленные дни сбрасываются\n'
        '• трафик и доступ к серверам снимаются\n'
        '• пользователь <b>отключается</b> в панели RemnaWave (не удаляется)\n\n'
        '✅ Сам пользователь и его тикеты <b>остаются</b> в боте.\n'
        'После этого он сможет купить тариф с нуля и выбрать срок.',
        reply_markup=get_confirmation_keyboard(f'admin_sub_reset_confirm_{user_id}{_sid}', back_cb, db_user.language),
    )
    await callback.answer()


@admin_required
@error_handler
async def confirm_subscription_reset(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    success = await _reset_user_subscription(db, user_id, db_user.id, subscription_id=subscription_id)

    message = (
        '✅ Подписка обнулена. Пользователь и его тикеты сохранены.' if success else '❌ Ошибка обнуления подписки'
    )
    await callback.message.edit_text(
        message,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
        ),
    )
    await callback.answer()


async def _reset_user_subscription(
    db: AsyncSession, user_id: int, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.services.subscription_service import reset_subscription_with_panel

        subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if not subscription:
            logger.error('Подписка не найдена для пользователя', user_id=user_id)
            return False

        user = await get_user_by_id(db, user_id)
        result = await reset_subscription_with_panel(db, user, subscription)

        logger.info(
            'Админ обнулил подписку пользователя (пользователь и тикеты сохранены)',
            admin_id=admin_id,
            user_id=user_id,
            subscription_id=subscription.id,
            panel_disabled=result.get('panel_disabled'),
        )
        return True

    except Exception as e:
        logger.error('Ошибка обнуления подписки', error=e)
        return False


@admin_required
@error_handler
async def activate_user_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    success = await _activate_user_subscription(db, user_id, db_user.id, subscription_id=subscription_id)

    if success:
        await callback.message.edit_text(
            '✅ Подписка пользователя активирована',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка активации подписки',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def grant_paid_subscription(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    user_id = int(callback.data.split('_')[-1])

    await state.update_data(granting_user_id=user_id)

    await callback.message.edit_text(
        '💎 <b>Выдача подписки</b>\n\n'
        'Введите количество дней подписки:\n'
        '• Например: 30, 90, 180, 365\n'
        '• Максимум: 730 дней\n\n'
        'Или нажмите /cancel для отмены',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text='30 дней', callback_data=f'admin_sub_grant_days_{user_id}_30'),
                    types.InlineKeyboardButton(text='90 дней', callback_data=f'admin_sub_grant_days_{user_id}_90'),
                ],
                [
                    types.InlineKeyboardButton(text='180 дней', callback_data=f'admin_sub_grant_days_{user_id}_180'),
                    types.InlineKeyboardButton(text='365 дней', callback_data=f'admin_sub_grant_days_{user_id}_365'),
                ],
                [types.InlineKeyboardButton(text='❌ Отмена', callback_data=f'admin_user_subscription_{user_id}')],
            ]
        ),
    )

    await state.set_state(AdminStates.granting_subscription)
    await callback.answer()


@admin_required
@error_handler
async def process_subscription_grant_days(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    parts = callback.data.split('_')
    user_id = int(parts[-2])
    days = int(parts[-1])

    success = await _grant_paid_subscription(db, user_id, days, db_user.id)

    if success:
        await callback.message.edit_text(
            f'✅ Пользователю выдана подписка на {days} дней',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='📱 К подписке', callback_data=f'admin_user_subscription_{user_id}'
                        )
                    ]
                ]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка выдачи подписки',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='📱 К подписке', callback_data=f'admin_user_subscription_{user_id}'
                        )
                    ]
                ]
            ),
        )

    await callback.answer()


@admin_required
@error_handler
async def process_subscription_grant_text(message: types.Message, db_user: User, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    user_id = data.get('granting_user_id')

    if not user_id:
        await message.answer('❌ Ошибка: пользователь не найден')
        await state.clear()
        return

    try:
        days = int(message.text.strip())

        if days <= 0 or days > 730:
            await message.answer('❌ Количество дней должно быть от 1 до 730')
            return

        success = await _grant_paid_subscription(db, user_id, days, db_user.id)

        if success:
            await message.answer(
                f'✅ Пользователю выдана подписка на {days} дней',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(
                                text='📱 К подписке', callback_data=f'admin_user_subscription_{user_id}'
                            )
                        ]
                    ]
                ),
            )
        else:
            await message.answer('❌ Ошибка выдачи подписки')

    except ValueError:
        await message.answer('❌ Введите корректное число дней')
        return

    await state.clear()


@admin_required
@error_handler
async def show_server_selection(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)
    await _show_servers_for_user(callback, user_id, db, subscription_id=subscription_id)
    await callback.answer()


async def _show_servers_for_user(
    callback: types.CallbackQuery, user_id: int, db: AsyncSession, subscription_id: int | None = None
):
    try:
        user = await get_user_by_id(db, user_id)
        current_squads = []
        if user:
            if subscription_id and settings.is_multi_tariff_enabled():
                from app.database.crud.subscription import get_subscription_by_id_for_user

                subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
            else:
                subscription = await _resolve_admin_subscription(db, user_id)
            if subscription:
                current_squads = subscription.connected_squads or []

        _sid = f'_s{subscription_id}' if subscription_id and settings.is_multi_tariff_enabled() else ''
        back_cb = (
            f'admin_user_sub_select_{user_id}_{subscription_id}'
            if subscription_id and settings.is_multi_tariff_enabled()
            else f'admin_user_subscription_{user_id}'
        )

        all_servers, _ = await get_all_server_squads(db, available_only=False)

        servers_to_show = []
        for server in all_servers:
            if server.is_available or server.squad_uuid in current_squads:
                servers_to_show.append(server)

        if not servers_to_show:
            await callback.message.edit_text(
                '❌ Доступные серверы не найдены',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)]]
                ),
            )
            return

        text = '🌍 <b>Управление серверами</b>\n\n'
        text += 'Нажмите на сервер чтобы добавить/убрать:\n'
        text += '✅ - выбранный сервер\n'
        text += '⚪ - доступный сервер\n'
        text += '🔒 - неактивный (только для уже назначенных)\n\n'

        keyboard = []
        selected_servers = [s for s in servers_to_show if s.squad_uuid in current_squads]
        available_servers = [s for s in servers_to_show if s.squad_uuid not in current_squads and s.is_available]
        inactive_servers = [s for s in servers_to_show if s.squad_uuid not in current_squads and not s.is_available]

        sorted_servers = selected_servers + available_servers + inactive_servers

        for server in sorted_servers[:20]:
            is_selected = server.squad_uuid in current_squads

            if is_selected:
                emoji = '✅'
            elif server.is_available:
                emoji = '⚪'
            else:
                emoji = '🔒'

            display_name = server.display_name
            if not server.is_available and not is_selected:
                display_name += ' (неактивный)'

            keyboard.append(
                [
                    types.InlineKeyboardButton(
                        text=f'{emoji} {display_name}',
                        callback_data=f'admin_user_toggle_server_{user_id}_{server.id}{_sid}',
                    )
                ]
            )

        if len(servers_to_show) > 20:
            text += f'\n📝 Показано первых 20 из {len(servers_to_show)} серверов'

        keyboard.append(
            [
                types.InlineKeyboardButton(text='✅ Готово', callback_data=back_cb),
                types.InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb),
            ]
        )

        await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))

    except Exception as e:
        logger.error('Ошибка показа серверов', error=e)


@admin_required
@error_handler
async def toggle_user_server(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    parts = callback.data.split('_')
    user_id = int(parts[4])
    server_id = int(parts[5])
    subscription_id = int(parts[6][1:]) if len(parts) > 6 and parts[6].startswith('s') else None

    try:
        user = await get_user_by_id(db, user_id)
        if subscription_id and settings.is_multi_tariff_enabled():
            from app.database.crud.subscription import get_subscription_by_id_for_user

            subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
        else:
            subscription = await _resolve_admin_subscription(db, user_id)
        if not user or not subscription:
            await callback.answer('❌ Пользователь или подписка не найдены', show_alert=True)
            return

        server = await get_server_squad_by_id(db, server_id)
        if not server:
            await callback.answer('❌ Сервер не найден', show_alert=True)
            return
        current_squads = list(subscription.connected_squads or [])

        if server.squad_uuid in current_squads:
            current_squads.remove(server.squad_uuid)
            action_text = 'удален'
        else:
            current_squads.append(server.squad_uuid)
            action_text = 'добавлен'

        subscription.connected_squads = current_squads
        subscription.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(subscription)

        try:
            await _push_narrow_change_to_panel(db, user, subscription, fields={'active_internal_squads'})
            logger.info('✅ Обновлены серверы в RemnaWave для пользователя', telegram_id=user.telegram_id)
        except Exception as rw_error:
            logger.error('❌ Ошибка обновления RemnaWave', rw_error=rw_error)

        logger.info(
            'Админ сервер для пользователя',
            db_user_id=db_user.id,
            display_name=server.display_name,
            action_text=action_text,
            user_id=user_id,
        )

        await refresh_server_selection_screen(callback, user_id, db_user, db, subscription_id=subscription_id)

    except Exception as e:
        logger.error('Ошибка переключения сервера', error=e)
        await callback.answer('❌ Ошибка изменения сервера', show_alert=True)


async def refresh_server_selection_screen(
    callback: types.CallbackQuery,
    user_id: int,
    db_user: User,
    db: AsyncSession,
    subscription_id: int | None = None,
):
    try:
        user = await get_user_by_id(db, user_id)
        current_squads = []
        if user:
            if subscription_id and settings.is_multi_tariff_enabled():
                from app.database.crud.subscription import get_subscription_by_id_for_user

                subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
            else:
                subscription = await _resolve_admin_subscription(db, user_id)
            if subscription:
                current_squads = subscription.connected_squads or []

        _sid = f'_s{subscription_id}' if subscription_id and settings.is_multi_tariff_enabled() else ''
        back_cb = (
            f'admin_user_sub_select_{user_id}_{subscription_id}'
            if subscription_id and settings.is_multi_tariff_enabled()
            else f'admin_user_subscription_{user_id}'
        )

        servers, _ = await get_all_server_squads(db, available_only=True)

        if not servers:
            await callback.message.edit_text(
                '❌ Доступные серверы не найдены',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)]]
                ),
            )
            return

        text = '🌍 <b>Управление серверами</b>\n\n'
        text += 'Нажмите на сервер чтобы добавить/убрать:\n\n'

        keyboard = []
        for server in servers[:15]:
            is_selected = server.squad_uuid in current_squads
            emoji = '✅' if is_selected else '⚪'

            keyboard.append(
                [
                    types.InlineKeyboardButton(
                        text=f'{emoji} {server.display_name}',
                        callback_data=f'admin_user_toggle_server_{user_id}_{server.id}{_sid}',
                    )
                ]
            )

        if len(servers) > 15:
            text += f'\n📝 Показано первых 15 из {len(servers)} серверов'

        keyboard.append(
            [
                types.InlineKeyboardButton(text='✅ Готово', callback_data=back_cb),
                types.InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb),
            ]
        )

        await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))

    except Exception as e:
        logger.error('Ошибка обновления экрана серверов', error=e)


async def _push_narrow_change_to_panel(db, user, subscription, *, fields: set[str]) -> None:
    """Донести до панели одно изменение подписки, не трогая соседние поля.

    Админские экраны правят по одному свойству — серверы, лимит устройств, лимит
    трафика. Отправлять при этом полное состояние подписки нельзя: заодно уедут
    дата и статус, которых админ не касался. Поэтому здесь узкий PATCH, но
    собранный тем же сервисом, что и все остальные, — иначе поля снова начнут
    расходиться. Описание аккаунта уезжает всегда: оно про пользователя, а не
    про подписку.
    """
    from app.services.grace_access_runtime import update_panel_user_grace_safe
    from app.services.panel_sync import push_subscription
    from app.services.panel_sync.fields import PANEL_ACCOUNT_METADATA_FIELDS

    remnawave_service = RemnaWaveService()
    try:
        await db.refresh(subscription, ['tariff'])
    except Exception as error:
        # Тариф нужен запросу к панели только для сквадов. Строка могла быть
        # отцеплена от сессии или удалена соседним проходом — тогда идём без
        # него: узкий PATCH трогает лишь то поле, ради которого позван.
        logger.debug('Не удалось догрузить тариф подписки перед PATCH', error=error)

    async with remnawave_service.get_api_client() as api:
        await push_subscription(
            api,
            user,
            subscription,
            db=db,
            only_fields=fields | PANEL_ACCOUNT_METADATA_FIELDS,
            reset_devices=False,
            create_if_missing=False,
            update_call=lambda **kwargs: update_panel_user_grace_safe(api, subscription.id, **kwargs),
        )


async def _resolve_admin_subscription(
    db: AsyncSession, user_id: int, subscription_id: int | None = None, tariff_id: int | None = None
) -> 'Subscription | None':
    """Resolve subscription for admin operations.

    In multi-tariff without explicit subscription_id:
    - If tariff_id provided → find active sub with that tariff only
    - 1 active sub → use it
    - Multiple → prefer non-daily with most days remaining
    - 0 active → return None
    """
    if settings.is_multi_tariff_enabled():
        if subscription_id:
            from app.database.crud.subscription import get_subscription_by_id_for_user

            return await get_subscription_by_id_for_user(db, subscription_id, user_id)

        from app.database.crud.subscription import get_active_subscriptions_by_user_id

        active_subs = await get_active_subscriptions_by_user_id(db, user_id)

        if not active_subs:
            return None

        # When buying a specific tariff, only match subscription with the same tariff_id
        if tariff_id is not None:
            matching = [s for s in active_subs if s.tariff_id == tariff_id]
            if matching:
                return matching[0]
            # No subscription for this tariff — must create a new one
            return None

        if len(active_subs) == 1:
            return active_subs[0]

        non_daily = [s for s in active_subs if not getattr(s, 'is_daily_tariff', False)]
        eligible = non_daily or active_subs
        selected = max(eligible, key=lambda s: s.days_left)
        logger.warning(
            'Admin operation: multiple active subscriptions, auto-selected best',
            user_id=user_id,
            selected_sub_id=selected.id,
            total_active=len(active_subs),
        )
        return selected
    from app.database.crud.subscription import get_subscription_by_user_id

    return await get_subscription_by_user_id(db, user_id)


async def _extend_subscription_by_days(
    db: AsyncSession, user_id: int, days: int, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.database.crud.subscription import extend_subscription
        from app.services.subscription_service import SubscriptionService

        subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if not subscription:
            logger.error('Подписка не найдена для пользователя', user_id=user_id)
            return False

        await extend_subscription(db, subscription, days, commit=False)
        now = datetime.now(UTC)
        if days < 0 and subscription.end_date <= now:
            subscription.status = SubscriptionStatus.EXPIRED.value
            subscription.grace_suppressed_until = now
        await db.commit()
        await db.refresh(subscription)

        subscription_service = SubscriptionService()
        await subscription_service.update_remnawave_user(db, subscription)

        if days > 0:
            logger.info('Админ продлил подписку пользователя на дней', admin_id=admin_id, user_id=user_id, days=days)
        else:
            logger.info(
                'Админ сократил подписку пользователя на дней', admin_id=admin_id, user_id=user_id, value=abs(days)
            )
        return True

    except Exception as e:
        logger.error('Ошибка продления подписки', error=e)
        return False


async def _add_subscription_traffic(
    db: AsyncSession, user_id: int, gb: int, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.database.crud.subscription import (
            add_subscription_traffic,
            reactivate_subscription,
        )
        from app.services.subscription_service import SubscriptionService

        subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if not subscription:
            logger.error('Подписка не найдена для пользователя', user_id=user_id)
            return False

        if gb == 0:
            subscription.traffic_limit_gb = 0
            await db.commit()
        else:
            await add_subscription_traffic(db, subscription, gb)

        # Реактивируем подписку если она была DISABLED/EXPIRED (например, после LIMITED/EXPIRED в RemnaWave)
        await reactivate_subscription(db, subscription)

        subscription_service = SubscriptionService()
        await subscription_service.update_remnawave_user(db, subscription)

        # Явно включаем пользователя на панели (PATCH может не снять LIMITED-статус)
        if subscription.status == 'active':
            panel_user_id = subscription.remnawave_id if settings.is_multi_tariff_enabled() else None
            if not panel_user_id:
                from app.database.crud.user import get_user_by_id

                user = await get_user_by_id(db, user_id)
                panel_user_id = getattr(user, 'remnawave_id', None)
            if panel_user_id:
                await subscription_service.enable_remnawave_user(panel_user_id)

        traffic_text = 'безлимитный' if gb == 0 else f'{gb} ГБ'
        logger.info('Админ добавил трафик пользователю', admin_id=admin_id, traffic_text=traffic_text, user_id=user_id)
        return True

    except Exception as e:
        logger.error('Ошибка добавления трафика', error=e)
        return False


async def _deactivate_user_subscription(
    db: AsyncSession, user_id: int, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.database.crud.subscription import (
            deactivate_subscription,
        )
        from app.services.subscription_service import SubscriptionService

        subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if not subscription:
            logger.error('Подписка не найдена для пользователя', user_id=user_id)
            return False

        await deactivate_subscription(db, subscription)

        subscription_service = SubscriptionService()
        panel_user_id = subscription.remnawave_id if settings.is_multi_tariff_enabled() else None
        if not panel_user_id:
            user = await get_user_by_id(db, user_id)
            panel_user_id = getattr(user, 'remnawave_id', None)
        if panel_user_id:
            await subscription_service.disable_remnawave_user(panel_user_id)

        logger.info('Админ деактивировал подписку пользователя', admin_id=admin_id, user_id=user_id)
        return True

    except Exception as e:
        logger.error('Ошибка деактивации подписки', error=e)
        return False


async def _activate_user_subscription(
    db: AsyncSession, user_id: int, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.database.crud.subscription import reconcile_tariff_traffic_limit
        from app.database.models import SubscriptionStatus
        from app.services.subscription_service import SubscriptionService

        subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if not subscription:
            logger.error('Подписка не найдена для пользователя', user_id=user_id)
            return False

        # Оверлей грейса, осевший в подписке (v4.10–4.11), — не её срок: вернуть до расчёта.
        from app.services.grace_access_echo import undo_grace_overlay_echo

        await undo_grace_overlay_echo(db, subscription)
        subscription.status = SubscriptionStatus.ACTIVE.value
        if subscription.end_date <= datetime.now(UTC):
            subscription.end_date = datetime.now(UTC) + timedelta(days=1)
            subscription.pending_panel_expire_at = subscription.end_date
        # Условия тарифа на новый срок: база тарифа + активные докупки.
        await reconcile_tariff_traffic_limit(db, subscription)

        await db.commit()
        await db.refresh(subscription)

        subscription_service = SubscriptionService()
        await subscription_service.update_remnawave_user(db, subscription)

        logger.info('Админ активировал подписку пользователя', admin_id=admin_id, user_id=user_id)
        return True

    except Exception as e:
        logger.error('Ошибка активации подписки', error=e)
        return False


async def _grant_paid_subscription(
    db: AsyncSession, user_id: int, days: int, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.config import settings
        from app.database.crud.subscription import create_paid_subscription
        from app.services.subscription_service import SubscriptionService

        existing_subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if existing_subscription and not settings.is_multi_tariff_enabled():
            logger.error('У пользователя уже есть подписка', user_id=user_id)
            return False

        trial_squads: list[str] = []

        try:
            from app.database.crud.server_squad import get_effective_tariff_squad_uuids

            trial_squads = await get_effective_tariff_squad_uuids(db, None)
        except Exception as error:
            logger.error('Не удалось подобрать сквад при выдаче подписки админом', admin_id=admin_id, error=error)

        forced_devices = None
        if not settings.is_devices_selection_enabled():
            forced_devices = settings.get_disabled_mode_device_limit()

        device_limit = settings.DEFAULT_DEVICE_LIMIT
        if forced_devices is not None:
            device_limit = forced_devices

        subscription = await create_paid_subscription(
            db=db,
            user_id=user_id,
            duration_days=days,
            traffic_limit_gb=settings.DEFAULT_TRAFFIC_LIMIT_GB,
            device_limit=device_limit,
            connected_squads=trial_squads,
            update_server_counters=True,
        )

        subscription_service = SubscriptionService()
        await subscription_service.create_remnawave_user(db, subscription)

        logger.info('Админ выдал платную подписку на дней пользователю', admin_id=admin_id, days=days, user_id=user_id)
        return True

    except Exception as e:
        logger.error('Ошибка выдачи платной подписки', error=e)
        return False


async def _calculate_subscription_period_price(
    db: AsyncSession,
    target_user: User,
    subscription: Subscription,
    period_days: int,
    subscription_service: SubscriptionService | None = None,
) -> int:
    """Рассчитывает стоимость подписки для администратора с учётом всех параметров."""
    from app.services.pricing_engine import pricing_engine

    # Загружаем тариф для корректного расчёта в тарифном режиме
    if subscription.tariff_id:
        try:
            await db.refresh(subscription, ['tariff'])
        except Exception as e:
            logger.warning('Не удалось загрузить тариф для расчёта цены', error=e)

    pricing = await pricing_engine.calculate_renewal_price(
        db,
        subscription,
        period_days,
        user=target_user,
    )
    return pricing.final_total


@admin_required
@error_handler
async def change_subscription_type(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    user_service = UserService()
    profile = await user_service.get_user_profile(db, user_id)

    if not profile:
        await callback.answer('❌ Пользователь или подписка не найдены', show_alert=True)
        return

    if subscription_id and settings.is_multi_tariff_enabled():
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = profile['subscription']

    if not subscription:
        await callback.answer('❌ Пользователь или подписка не найдены', show_alert=True)
        return

    current_type = '🎁 Триал' if subscription.is_trial else '💎 Платная'

    text = '🔄 <b>Смена типа подписки</b>\n\n'
    text += f'👤 {html.escape(profile["user"].full_name)}\n'
    text += f'📱 Текущий тип: {current_type}\n\n'
    text += 'Выберите новый тип подписки:'

    keyboard = []

    if subscription.is_trial:
        keyboard.append(
            [InlineKeyboardButton(text='💎 Сделать платной', callback_data=f'admin_sub_type_paid_{user_id}{_sid}')]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton(text='🎁 Сделать триальной', callback_data=f'admin_sub_type_trial_{user_id}{_sid}')]
        )

    keyboard.append([InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


async def _admin_buy_periods(db: AsyncSession, subscription: Subscription) -> list[int] | None:
    """Use the selected tariff's periods; None requires an explicit tariff choice."""
    if subscription.tariff_id:
        from app.database.crud.tariff import get_tariff_by_id

        tariff = await get_tariff_by_id(db, subscription.tariff_id)
        return tariff.get_available_periods() if tariff else None
    return None


def _parse_admin_buy_callback(callback_data: str) -> tuple[int, int, int | None, int | None]:
    """Keep legacy callbacks valid while retaining an explicitly pinned subscription."""
    parts = callback_data.split('_')
    subscription_id = None
    if parts[-1].startswith('s'):
        subscription_id = int(parts.pop()[1:])
    return int(parts[4]), int(parts[5]), int(parts[6]) if len(parts) > 6 else None, subscription_id


@admin_required
@error_handler
async def admin_buy_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    _sid = f'_s{subscription_id}' if subscription_id is not None else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    user_service = UserService()
    profile = await user_service.get_user_profile(db, user_id)

    if not profile:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    target_user = profile['user']

    if subscription_id is not None:
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = profile['subscription']

    if not subscription:
        await callback.answer('❌ У пользователя нет подписки', show_alert=True)
        return

    available_periods = await _admin_buy_periods(db, subscription)
    if available_periods is None:
        await callback.answer('❌ Сначала выберите тариф для подписки', show_alert=True)
        return

    subscription_service = SubscriptionService()
    period_buttons = []

    for period in available_periods:
        try:
            price_kopeks = await _calculate_subscription_period_price(
                db,
                target_user,
                subscription,
                period,
                subscription_service=subscription_service,
            )
        except Exception as e:
            logger.error(
                'Ошибка расчёта стоимости подписки для пользователя и периода дней',
                telegram_id=target_user.telegram_id,
                period=period,
                e=e,
            )
            continue

        period_buttons.append(
            [
                types.InlineKeyboardButton(
                    text=f'{period} дней ({settings.format_price(price_kopeks)})',
                    callback_data=f'admin_buy_sub_confirm_{user_id}_{period}_{price_kopeks}{_sid}',
                )
            ]
        )

    if not period_buttons:
        await callback.answer('❌ Не удалось рассчитать стоимость подписки', show_alert=True)
        return

    period_buttons.append([types.InlineKeyboardButton(text='❌ Отмена', callback_data=back_cb)])

    text = '💳 <b>Покупка подписки для пользователя</b>\n\n'
    target_user_link = user_html_link(target_user)
    target_user_id_display = target_user.telegram_id or target_user.email or f'#{target_user.id}'
    text += f'👤 {target_user_link} (ID: {target_user_id_display})\n'
    text += f'💰 Баланс пользователя: {settings.format_price(target_user.balance_kopeks)}\n\n'
    traffic_text = 'Безлимит' if (subscription.traffic_limit_gb or 0) <= 0 else f'{subscription.traffic_limit_gb} ГБ'
    devices_limit = subscription.device_limit
    if devices_limit is None:
        devices_limit = settings.DEFAULT_DEVICE_LIMIT
    servers_count = len(subscription.connected_squads or [])
    text += f'📶 Трафик: {traffic_text}\n'
    text += f'📱 Устройства: {Texts.format_device_limit(devices_limit)}\n'
    text += f'🌐 Серверов: {servers_count}\n\n'
    text += 'Выберите период подписки:\n'

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=period_buttons))
    await callback.answer()


@admin_required
@error_handler
async def admin_buy_subscription_confirm(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, period_days, price_kopeks_from_callback, subscription_id = _parse_admin_buy_callback(callback.data)
    _sid = f'_s{subscription_id}' if subscription_id is not None else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id is not None
        else f'admin_user_subscription_{user_id}'
    )

    user_service = UserService()
    profile = await user_service.get_user_profile(db, user_id)

    if not profile:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    target_user = profile['user']
    if subscription_id is not None:
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = profile['subscription']

    if not subscription:
        await callback.answer('❌ У пользователя нет подписки', show_alert=True)
        return

    available_periods = await _admin_buy_periods(db, subscription)
    if available_periods is None:
        await callback.answer('❌ Сначала выберите тариф для подписки', show_alert=True)
        return
    if period_days not in available_periods:
        await callback.answer('❌ Этот период больше недоступен. Выберите период заново', show_alert=True)
        return

    subscription_service = SubscriptionService()

    try:
        price_kopeks = await _calculate_subscription_period_price(
            db,
            target_user,
            subscription,
            period_days,
            subscription_service=subscription_service,
        )
    except Exception as e:
        logger.error(
            'Ошибка расчёта стоимости подписки при подтверждении админом для пользователя',
            telegram_id=target_user.telegram_id,
            e=e,
        )
        await callback.answer('❌ Не удалось рассчитать стоимость подписки', show_alert=True)
        return

    if price_kopeks_from_callback is not None and price_kopeks_from_callback != price_kopeks:
        logger.info(
            'Стоимость подписки для пользователя изменилась с до при подтверждении',
            telegram_id=target_user.telegram_id,
            price_kopeks_from_callback=price_kopeks_from_callback,
            price_kopeks=price_kopeks,
        )

    if target_user.balance_kopeks < price_kopeks:
        missing_kopeks = price_kopeks - target_user.balance_kopeks
        # Без округления — иначе при не хватке <50 копеек все три суммы покажутся
        # одинаковыми и админ увидит «не хватает 0 ₽».
        await callback.message.edit_text(
            f'❌ Недостаточно средств на балансе пользователя\n\n'
            f'💰 Баланс пользователя: {settings.format_price(target_user.balance_kopeks, round_kopeks=False)}\n'
            f'💳 Стоимость подписки: {settings.format_price(price_kopeks, round_kopeks=False)}\n'
            f'📉 Не хватает: {settings.format_price(missing_kopeks, round_kopeks=False)}\n\n'
            f'Пополните баланс пользователя перед покупкой.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад к подписке', callback_data=back_cb)]]
            ),
        )
        await callback.answer()
        return

    text = '💳 <b>Подтверждение покупки подписки</b>\n\n'
    target_user_link = user_html_link(target_user)
    target_user_id_display = target_user.telegram_id or target_user.email or f'#{target_user.id}'
    text += f'👤 {target_user_link} (ID: {target_user_id_display})\n'
    text += f'📅 Период подписки: {period_days} дней\n'
    text += f'💰 Стоимость: {settings.format_price(price_kopeks)}\n'
    text += f'💰 Баланс пользователя: {settings.format_price(target_user.balance_kopeks)}\n\n'
    traffic_text = 'Безлимит' if (subscription.traffic_limit_gb or 0) <= 0 else f'{subscription.traffic_limit_gb} ГБ'
    devices_limit = subscription.device_limit
    if devices_limit is None:
        devices_limit = settings.DEFAULT_DEVICE_LIMIT
    servers_count = len(subscription.connected_squads or [])
    text += f'📶 Трафик: {traffic_text}\n'
    text += f'📱 Устройства: {Texts.format_device_limit(devices_limit)}\n'
    text += f'🌐 Серверов: {servers_count}\n\n'
    text += 'Вы уверены, что хотите купить подписку для этого пользователя?'

    keyboard = [
        [
            types.InlineKeyboardButton(
                text='✅ Подтвердить',
                callback_data=f'admin_buy_sub_execute_{user_id}_{period_days}_{price_kopeks}{_sid}',
            )
        ],
        [types.InlineKeyboardButton(text='❌ Отмена', callback_data=f'admin_sub_buy_{user_id}{_sid}')],
    ]

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@admin_required
@error_handler
async def admin_buy_subscription_execute(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    user_id, period_days, price_kopeks_from_callback, subscription_id = _parse_admin_buy_callback(callback.data)
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id is not None
        else f'admin_user_subscription_{user_id}'
    )

    user_service = UserService()
    profile = await user_service.get_user_profile(db, user_id)

    if not profile:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    target_user = profile['user']
    if subscription_id is not None:
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = profile['subscription']

    if not subscription:
        await callback.answer('❌ У пользователя нет подписки', show_alert=True)
        return

    available_periods = await _admin_buy_periods(db, subscription)
    if available_periods is None:
        await callback.answer('❌ Сначала выберите тариф для подписки', show_alert=True)
        return
    if period_days not in available_periods:
        await callback.answer('❌ Этот период больше недоступен. Выберите период заново', show_alert=True)
        return

    subscription_service = SubscriptionService()

    # TOCTOU protection: lock user row before pricing to prevent concurrent balance modifications
    import asyncio

    from app.database.crud.user import lock_user_for_pricing

    try:
        target_user = await lock_user_for_pricing(db, target_user.id)

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        locked_subscription_id = subscription_id if subscription_id is not None else subscription.id
        result = await db.execute(
            select(Subscription)
            .where(Subscription.id == locked_subscription_id, Subscription.user_id == user_id)
            .options(selectinload(Subscription.tariff))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            await db.rollback()
            await callback.answer('❌ У пользователя нет выбранной подписки', show_alert=True)
            return
        available_periods = await _admin_buy_periods(db, subscription)
        if available_periods is None or period_days not in available_periods:
            await db.rollback()
            await callback.answer('❌ Период или тариф больше недоступен. Выберите заново', show_alert=True)
            return

        try:
            price_kopeks = await _calculate_subscription_period_price(
                db,
                target_user,
                subscription,
                period_days,
                subscription_service=subscription_service,
            )
        except Exception as e:
            logger.error(
                'Ошибка расчёта стоимости подписки при списании средств админом для пользователя',
                telegram_id=target_user.telegram_id,
                e=e,
            )
            await db.rollback()
            await callback.answer('❌ Не удалось рассчитать стоимость подписки', show_alert=True)
            return

        if price_kopeks_from_callback is not None and price_kopeks_from_callback != price_kopeks:
            await db.rollback()
            await callback.answer(
                '❌ Стоимость изменилась. Выберите период заново и подтвердите новую цену',
                show_alert=True,
            )
            return

        if target_user.balance_kopeks < price_kopeks:
            await db.rollback()
            await callback.answer('❌ Недостаточно средств на балансе пользователя', show_alert=True)
            return

        from app.database.crud.user import subtract_user_balance

        success = await subtract_user_balance(
            db,
            target_user,
            price_kopeks,
            f'Покупка подписки на {period_days} дней (администратор)',
            mark_as_paid_subscription=True,
            commit=False,
        )

        if not success:
            await db.rollback()
            await callback.answer('❌ Ошибка списания средств', show_alert=True)
            return

        if subscription:
            # Оверлей грейса, осевший в подписке (v4.10–4.11), — не её срок: вернуть до расчёта.
            from app.services.grace_access_echo import undo_grace_overlay_echo

            await undo_grace_overlay_echo(db, subscription)
            current_time = datetime.now(UTC)
            bonus_period = timedelta()

            from app.database.crud.subscription import should_carry_trial_remaining_days

            if subscription.is_trial and should_carry_trial_remaining_days() and subscription.end_date:
                remaining_trial_delta = subscription.end_date - current_time
                if remaining_trial_delta.total_seconds() > 0:
                    bonus_period = remaining_trial_delta
                    logger.info(
                        'Админ продлевает подписку: добавляем оставшееся время триала пользователю',
                        bonus_period=bonus_period,
                        telegram_id=target_user.telegram_id,
                    )

            extension_base_date = current_time
            if not subscription.is_trial and subscription.end_date and subscription.end_date > current_time:
                extension_base_date = subscription.end_date
            else:
                subscription.start_date = current_time
                begin_traffic_cycle(subscription, current_time)

            subscription.end_date = extension_base_date + timedelta(days=period_days) + bonus_period
            subscription.pending_panel_expire_at = subscription.end_date
            subscription.status = SubscriptionStatus.ACTIVE.value
            subscription.updated_at = current_time

            if subscription.is_trial or not subscription.is_active:
                was_trial = subscription.is_trial
                subscription.is_trial = False
                if subscription.tariff_id is None:
                    if subscription.traffic_limit_gb != 0:
                        subscription.traffic_limit_gb = 0
                    subscription.device_limit = settings.DEFAULT_DEVICE_LIMIT
                if was_trial:
                    subscription.traffic_used_gb = 0.0

            from app.database.crud.transaction import create_transaction, emit_transaction_side_effects

            transaction = await create_transaction(
                db=db,
                user_id=target_user.id,
                type=TransactionType.SUBSCRIPTION_PAYMENT,
                amount_kopeks=price_kopeks,
                description=f'Продление подписки на {period_days} дней (администратор)',
                commit=False,
            )
            await db.commit()
            await db.refresh(subscription)
            from app.database.models import PaymentMethod

            await emit_transaction_side_effects(
                db,
                transaction,
                amount_kopeks=price_kopeks,
                user_id=user_id,
                type=TransactionType.SUBSCRIPTION_PAYMENT,
                payment_method=PaymentMethod.BALANCE,
                description=f'Продление подписки на {period_days} дней (администратор)',
            )

            try:
                from app.services.panel_sync import push_subscription
                from app.services.remnawave_service import RemnaWaveService

                remnawave_service = RemnaWaveService()

                # Тариф нужен сервису для стратегии сброса трафика и внешнего
                # сквада: без предзагрузки обращение к нему упадёт в async-контексте.
                try:
                    await db.refresh(subscription, ['tariff'])
                except Exception:
                    logger.debug('Ignored error in admin_buy_subscription_execute', exc_info=True)

                async with remnawave_service.get_api_client() as api:
                    from app.services.grace_access_runtime import (
                        create_panel_user_grace_safe,
                        update_panel_user_grace_safe,
                    )

                    result = await push_subscription(
                        api,
                        target_user,
                        subscription,
                        db=db,
                        update_call=lambda **kwargs: update_panel_user_grace_safe(api, subscription.id, **kwargs),
                        create_call=lambda **kwargs: create_panel_user_grace_safe(
                            api,
                            subscription.id,
                            adopt_short_uuid=subscription.remnawave_short_uuid,
                            **kwargs,
                        ),
                    )
                    remnawave_user = result.panel_user
                    # Идентичность обязана сохраниться: без неё следующий админский
                    # extend снова уйдёт в create-ветку и наплодит дублей в панели.
                    await db.commit()

                if remnawave_user:
                    logger.info('Пользователь успешно обновлен в RemnaWave', telegram_id=target_user.telegram_id)
                else:
                    logger.error('Ошибка обновления пользователя в RemnaWave', telegram_id=target_user.telegram_id)
            except Exception as e:
                logger.error('Ошибка работы с RemnaWave для пользователя', telegram_id=target_user.telegram_id, error=e)

            message = f'✅ Подписка пользователя продлена на {period_days} дней'
        else:
            message = '❌ Ошибка: у пользователя нет существующей подписки'

        target_user_link = user_html_link(target_user)
        target_user_id_display = target_user.telegram_id or target_user.email or f'#{target_user.id}'
        await callback.message.edit_text(
            f'{message}\n\n'
            f'👤 {target_user_link} (ID: {target_user_id_display})\n'
            f'💰 Списано: {settings.format_price(price_kopeks)}\n'
            f'📅 Подписка действительна до: {format_datetime(subscription.end_date)}',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад к подписке', callback_data=back_cb)]]
            ),
            parse_mode='HTML',
        )

        try:
            if callback.bot and target_user.telegram_id and settings.is_notifications_enabled():
                tariff_line = ''
                if settings.is_multi_tariff_enabled() and getattr(subscription, 'tariff', None):
                    tariff_line = f'\n📦 Тариф: «{subscription.tariff.name}»'
                await callback.bot.send_message(
                    chat_id=target_user.telegram_id,
                    text=f'✅ <b>Подписка продлена до {format_datetime(subscription.end_date)}</b>{tariff_line}\n\n'
                    f'Продлили на {period_days} дн., с баланса списано {settings.format_price(price_kopeks)}.',
                    parse_mode='HTML',
                    reply_markup=keyboard(subscription_button(get_texts(target_user.language))),
                )
        except Exception as e:
            user_id_display = target_user.telegram_id or target_user.email or f'#{target_user.id}'
            logger.error('Ошибка отправки уведомления пользователю', user_id_display=user_id_display, error=e)

        await callback.answer()

    except asyncio.CancelledError:
        await db.rollback()
        raise
    except Exception as e:
        logger.error('Ошибка покупки подписки администратором', error=e)
        await db.rollback()
        await callback.answer('❌ Ошибка при покупке подписки', show_alert=True)


# ==================== Покупка тарифа администратором ====================


@admin_required
@error_handler
async def change_subscription_type_confirm(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    parts = callback.data.split('_')
    # callback: admin_sub_type_{new_type}_{user_id} or admin_sub_type_{new_type}_{user_id}_s{sub_id}
    new_type = parts[3]  # 'paid' or 'trial'
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    success = await _change_subscription_type(db, user_id, new_type, db_user.id, subscription_id)

    if success:
        type_text = 'платной' if new_type == 'paid' else 'триальной'
        await callback.message.edit_text(
            f'✅ Тип подписки успешно изменен на {type_text}',
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )
    else:
        await callback.message.edit_text(
            '❌ Ошибка изменения типа подписки',
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    await callback.answer()


async def _change_subscription_type(
    db: AsyncSession, user_id: int, new_type: str, admin_id: int, subscription_id: int | None = None
) -> bool:
    try:
        from app.services.subscription_service import SubscriptionService

        if subscription_id is not None and (subscription_id <= 0 or not settings.is_multi_tariff_enabled()):
            return False
        subscription = await _resolve_admin_subscription(db, user_id, subscription_id)
        if not subscription:
            logger.error('Подписка не найдена для пользователя', user_id=user_id)
            return False

        new_is_trial = new_type == 'trial'

        if subscription.is_trial == new_is_trial:
            logger.info('Тип подписки уже установлен корректно для пользователя', user_id=user_id)
            return True

        old_type = 'триальной' if subscription.is_trial else 'платной'
        new_type_text = 'триальной' if new_is_trial else 'платной'

        was_trial = subscription.is_trial
        subscription.is_trial = new_is_trial
        subscription.updated_at = datetime.now(UTC)

        if not new_is_trial and was_trial:
            user = await get_user_by_id(db, user_id)
            if user:
                user.has_had_paid_subscription = True

        await db.commit()

        subscription_service = SubscriptionService()
        await subscription_service.update_remnawave_user(db, subscription)

        logger.info(
            'Админ изменил тип подписки пользователя',
            admin_id=admin_id,
            user_id=user_id,
            old_type=old_type,
            new_type_text=new_type_text,
        )
        return True

    except Exception as e:
        logger.error('Ошибка изменения типа подписки', error=e)
        await db.rollback()
        return False


# =============================================================================
# Смена тарифа пользователя администратором
# =============================================================================


@admin_required
@error_handler
async def show_admin_tariff_change(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Показывает список доступных тарифов для смены."""
    user_id, subscription_id = _extract_admin_sub_context(callback.data)

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    user = await get_user_by_id(db, user_id)
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    if subscription_id and settings.is_multi_tariff_enabled():
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = await _resolve_admin_subscription(db, user_id)

    if not subscription:
        await callback.answer('❌ У пользователя нет подписки', show_alert=True)
        return

    # Получаем все активные тарифы
    tariffs = await get_all_tariffs(db, include_inactive=False)

    if not tariffs:
        await callback.message.edit_text(
            '❌ <b>Нет доступных тарифов</b>\n\nСоздайте тарифы в разделе управления тарифами.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)]]
            ),
        )
        await callback.answer()
        return

    # Текущий тариф
    current_tariff = None
    if subscription.tariff_id:
        current_tariff = await get_tariff_by_id(db, subscription.tariff_id)

    text = '📦 <b>Смена тарифа пользователя</b>\n\n'
    user_link = user_html_link(user)
    text += f'👤 {user_link}\n\n'

    if current_tariff:
        text += f'<b>Текущий тариф:</b> {html.escape(current_tariff.name)}\n\n'
    else:
        text += '<b>Текущий тариф:</b> не установлен\n\n'

    text += 'Выберите новый тариф:\n'

    keyboard = []
    for tariff in tariffs:
        # Отмечаем текущий тариф
        prefix = '✅ ' if current_tariff and tariff.id == current_tariff.id else ''

        # Описание тарифа
        traffic_str = '♾️' if tariff.traffic_limit_gb == 0 else f'{tariff.traffic_limit_gb} ГБ'
        servers_count = len(tariff.allowed_squads) if tariff.allowed_squads else 0

        button_text = (
            f'{prefix}{tariff.name} ({Texts.format_device_limit(tariff.device_limit)} устр., '
            f'{traffic_str}, {servers_count} серв.)'
        )

        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=button_text, callback_data=f'admin_sub_tariff_select_{tariff.id}_{user_id}{_sid}'
                )
            ]
        )

    keyboard.append([types.InlineKeyboardButton(text='⬅️ Назад', callback_data=back_cb)])

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@admin_required
@error_handler
async def select_admin_tariff_change(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Подтверждение выбора тарифа."""
    parts = callback.data.split('_')
    # admin_sub_tariff_select_{tariff_id}_{user_id} or admin_sub_tariff_select_{tariff_id}_{user_id}_s{sub_id}
    user_id, subscription_id = _extract_admin_sub_context(callback.data)
    # tariff_id is always the part right before user_id (before optional subscription_id)
    if subscription_id:
        tariff_id = int(parts[-3])
    else:
        tariff_id = int(parts[-2])

    _sid = f'_s{subscription_id}' if subscription_id else ''
    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    user = await get_user_by_id(db, user_id)
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    tariff = await get_tariff_by_id(db, tariff_id)
    if not tariff:
        await callback.answer('❌ Тариф не найден', show_alert=True)
        return

    if subscription_id and settings.is_multi_tariff_enabled():
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = await _resolve_admin_subscription(db, user_id)

    if not subscription:
        await callback.answer('❌ У пользователя нет подписки', show_alert=True)
        return

    # Проверяем, если это тот же тариф
    if subscription.tariff_id == tariff_id:
        await callback.answer('ℹ️ Этот тариф уже установлен', show_alert=True)
        return

    traffic_str = '♾️' if tariff.traffic_limit_gb == 0 else f'{tariff.traffic_limit_gb} ГБ'
    servers_count = len(tariff.allowed_squads) if tariff.allowed_squads else 0

    text = '📦 <b>Подтверждение смены тарифа</b>\n\n'
    user_link = user_html_link(user)
    text += f'👤 {user_link}\n\n'
    text += f'<b>Новый тариф:</b> {html.escape(tariff.name)}\n'
    text += f'• Устройства: {Texts.format_device_limit(tariff.device_limit)}\n'
    text += f'• Трафик: {traffic_str}\n'
    text += f'• Серверы: {servers_count}\n\n'
    text += '⚠️ Параметры подписки будут обновлены в соответствии с тарифом.\n'
    text += 'Дата окончания подписки не изменится.'

    keyboard = [
        [
            types.InlineKeyboardButton(
                text='✅ Подтвердить', callback_data=f'admin_sub_tariff_confirm_{tariff_id}_{user_id}{_sid}'
            ),
            types.InlineKeyboardButton(text='❌ Отмена', callback_data=back_cb),
        ]
    ]

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@admin_required
@error_handler
async def confirm_admin_tariff_change(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Применяет смену тарифа."""
    parts = callback.data.split('_')
    # admin_sub_tariff_confirm_{tariff_id}_{user_id} or admin_sub_tariff_confirm_{tariff_id}_{user_id}_s{sub_id}
    user_id, subscription_id = _extract_admin_sub_context(callback.data)
    if subscription_id:
        tariff_id = int(parts[-3])
    else:
        tariff_id = int(parts[-2])

    back_cb = (
        f'admin_user_sub_select_{user_id}_{subscription_id}'
        if subscription_id
        else f'admin_user_subscription_{user_id}'
    )

    user = await get_user_by_id(db, user_id)
    if not user:
        await callback.answer('❌ Пользователь не найден', show_alert=True)
        return

    tariff = await get_tariff_by_id(db, tariff_id)
    if not tariff:
        await callback.answer('❌ Тариф не найден', show_alert=True)
        return

    if subscription_id and settings.is_multi_tariff_enabled():
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, subscription_id, user_id)
    else:
        subscription = await _resolve_admin_subscription(db, user_id)

    if not subscription:
        await callback.answer('❌ У пользователя нет подписки', show_alert=True)
        return

    try:
        old_tariff_id = subscription.tariff_id

        # Preserve extra purchased devices above the old tariff's base limit
        from app.database.crud.subscription import calc_device_limit_on_admin_tariff_change

        old_tariff = await get_tariff_by_id(db, subscription.tariff_id) if subscription.tariff_id else None

        subscription.tariff_id = tariff.id
        subscription.device_limit = calc_device_limit_on_admin_tariff_change(
            current_device_limit=subscription.device_limit,
            old_tariff_device_limit=old_tariff.device_limit if old_tariff else None,
            new_tariff_device_limit=tariff.device_limit,
            max_device_limit=tariff.max_device_limit,
            old_tariff=old_tariff,
            new_tariff=tariff,
        )

        subscription.traffic_limit_gb = tariff.traffic_limit_gb
        subscription.connected_squads = tariff.allowed_squads or []
        subscription.updated_at = datetime.now(UTC)

        # Сбрасываем докупленный трафик при смене тарифа
        from sqlalchemy import delete as sql_delete

        from app.database.models import TrafficPurchase

        await db.execute(sql_delete(TrafficPurchase).where(TrafficPurchase.subscription_id == subscription.id))
        subscription.purchased_traffic_gb = 0
        subscription.traffic_reset_at = None

        # Сброс использованного трафика по админ-настройке
        if settings.RESET_TRAFFIC_ON_TARIFF_SWITCH:
            subscription.traffic_used_gb = 0.0

        # Записываем транзакцию о смене тарифа
        from app.database.crud.transaction import create_transaction

        await create_transaction(
            db=db,
            user_id=user.id,
            type=TransactionType.SUBSCRIPTION_PAYMENT,
            amount_kopeks=0,
            description=f"Смена тарифа администратором на '{tariff.name}'",
            commit=False,
        )

        await db.commit()

        # Синхронизируем с RemnaWave (сброс трафика по админ-настройке)
        subscription_service = SubscriptionService()
        await subscription_service.update_remnawave_user(
            db,
            subscription,
            reset_traffic=settings.RESET_TRAFFIC_ON_TARIFF_SWITCH,
            reset_reason='смена тарифа (админ)',
            sync_squads=True,
        )

        logger.info(
            'Админ изменил тариф пользователя',
            db_user_id=db_user.id,
            user_id=user_id,
            old_tariff_id=old_tariff_id,
            tariff_id=tariff_id,
            tariff_name=tariff.name,
        )

        await callback.message.edit_text(
            f'✅ <b>Тариф успешно изменен</b>\n\n'
            f'Новый тариф: <b>{html.escape(tariff.name)}</b>\n'
            f'• Устройства: {Texts.format_device_limit(subscription.device_limit)}\n'
            f'• Трафик: {"♾️" if tariff.traffic_limit_gb == 0 else f"{tariff.traffic_limit_gb} ГБ"}\n'
            f'• Серверы: {len(tariff.allowed_squads) if tariff.allowed_squads else 0}',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    except Exception as e:
        logger.error('Ошибка смены тарифа', error=e)
        await db.rollback()

        await callback.message.edit_text(
            f'❌ <b>Ошибка смены тарифа</b>\n\nДетали: {html.escape(str(e))}',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='📱 К подписке', callback_data=back_cb)]]
            ),
        )

    await callback.answer()


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_users_menu, F.data == 'admin_users')

    dp.callback_query.register(show_users_list, F.data == 'admin_users_list')

    dp.callback_query.register(show_user_subscription, F.data.startswith('admin_user_subscription_'))

    dp.callback_query.register(admin_select_user_subscription, F.data.startswith('admin_user_sub_select_'))

    dp.callback_query.register(show_user_transactions, F.data.startswith('admin_user_transactions_'))

    dp.callback_query.register(block_user, F.data.startswith('admin_user_block_confirm_'))

    dp.callback_query.register(delete_user_account, F.data.startswith('admin_user_delete_confirm_'))

    dp.callback_query.register(confirm_user_block, F.data.startswith('admin_user_block_') & ~F.data.contains('confirm'))

    dp.callback_query.register(unblock_user, F.data.startswith('admin_user_unblock_confirm_'))

    dp.callback_query.register(
        confirm_user_unblock, F.data.startswith('admin_user_unblock_') & ~F.data.contains('confirm')
    )

    dp.callback_query.register(
        confirm_user_delete, F.data.startswith('admin_user_delete_') & ~F.data.contains('confirm')
    )

    # Регистрация хендлеров ограничений пользователя
    dp.callback_query.register(show_user_restrictions, F.data.startswith('admin_user_restrictions_'))

    dp.callback_query.register(toggle_user_restriction_topup, F.data.startswith('admin_user_restriction_toggle_topup_'))

    dp.callback_query.register(
        toggle_user_restriction_subscription, F.data.startswith('admin_user_restriction_toggle_sub_')
    )

    dp.callback_query.register(ask_restriction_reason, F.data.startswith('admin_user_restriction_reason_'))

    dp.callback_query.register(clear_user_restrictions, F.data.startswith('admin_user_restriction_clear_'))

    dp.message.register(save_restriction_reason, AdminStates.editing_user_restriction_reason)

    dp.callback_query.register(handle_users_list_pagination_fixed, F.data.startswith('admin_users_list_page_'))

    dp.callback_query.register(start_user_search, F.data == 'admin_users_search')

    dp.message.register(process_user_search, AdminStates.waiting_for_user_search)

    dp.callback_query.register(show_user_management, F.data.startswith('admin_user_manage_'))

    dp.callback_query.register(start_balance_edit, F.data.startswith('admin_user_balance_'))

    dp.message.register(process_balance_edit, AdminStates.editing_user_balance)

    dp.callback_query.register(
        show_user_referrals, F.data.startswith('admin_user_referrals_') & ~F.data.contains('_edit')
    )

    dp.callback_query.register(
        extend_user_subscription,
        F.data.startswith('admin_sub_extend_') & ~F.data.contains('days') & ~F.data.contains('confirm'),
    )

    dp.callback_query.register(process_subscription_extension_days, F.data.startswith('admin_sub_extend_days_'))

    dp.message.register(process_subscription_extension_text, AdminStates.extending_subscription)

    dp.callback_query.register(
        add_subscription_traffic, F.data.startswith('admin_sub_traffic_') & ~F.data.contains('add')
    )

    dp.callback_query.register(process_traffic_addition_button, F.data.startswith('admin_sub_traffic_add_'))

    dp.message.register(process_traffic_addition_text, AdminStates.adding_traffic)

    dp.callback_query.register(
        deactivate_user_subscription, F.data.startswith('admin_sub_deactivate_') & ~F.data.contains('confirm')
    )

    dp.callback_query.register(confirm_subscription_deactivation, F.data.startswith('admin_sub_deactivate_confirm_'))

    dp.callback_query.register(
        reset_user_subscription, F.data.startswith('admin_sub_reset_') & ~F.data.contains('confirm')
    )

    dp.callback_query.register(confirm_subscription_reset, F.data.startswith('admin_sub_reset_confirm_'))

    dp.callback_query.register(activate_user_subscription, F.data.startswith('admin_sub_activate_'))

    dp.callback_query.register(
        grant_paid_subscription,
        F.data.startswith('admin_sub_grant_') & ~F.data.contains('trial') & ~F.data.contains('days'),
    )

    dp.callback_query.register(process_subscription_grant_days, F.data.startswith('admin_sub_grant_days_'))

    dp.message.register(process_subscription_grant_text, AdminStates.granting_subscription)

    dp.callback_query.register(show_server_selection, F.data.startswith('admin_user_change_server_'))

    dp.callback_query.register(
        toggle_user_server,
        F.data.startswith('admin_user_toggle_server_') & ~F.data.endswith('_add') & ~F.data.endswith('_remove'),
    )

    # Смена тарифа пользователя
    dp.callback_query.register(show_admin_tariff_change, F.data.startswith('admin_sub_change_tariff_'))

    dp.callback_query.register(select_admin_tariff_change, F.data.startswith('admin_sub_tariff_select_'))

    dp.callback_query.register(confirm_admin_tariff_change, F.data.startswith('admin_sub_tariff_confirm_'))

    dp.callback_query.register(change_subscription_type, F.data.startswith('admin_sub_change_type_'))

    dp.callback_query.register(change_subscription_type_confirm, F.data.startswith('admin_sub_type_'))

    # Регистрация обработчика покупки подписки администратором
    dp.callback_query.register(admin_buy_subscription, F.data.startswith('admin_sub_buy_'))

    # Регистрация дополнительных обработчиков для покупки подписки
    dp.callback_query.register(admin_buy_subscription_confirm, F.data.startswith('admin_buy_sub_confirm_'))

    dp.callback_query.register(admin_buy_subscription_execute, F.data.startswith('admin_buy_sub_execute_'))
