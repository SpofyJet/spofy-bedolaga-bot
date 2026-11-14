import html
import json
from datetime import UTC, datetime

import structlog
from aiogram import Dispatcher, F, types
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.referral import (
    get_referral_statistics,
)
from app.database.crud.user import get_user_by_id
from app.database.models import User, WithdrawalRequest, WithdrawalRequestStatus
from app.keyboards.withdrawal import get_withdrawal_request_keyboard
from app.services.referral_withdrawal_service import referral_withdrawal_service
from app.services.withdrawal_notifications import DEFAULT_BOT_REJECT_COMMENT, notify_user_about_withdrawal_status
from app.utils.chat_scope import callback_from_group
from app.utils.decorators import admin_required, error_handler
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)


from app.services.referral_reward_service import format_reward_total as _paid_line


def _levels_breakdown_block(by_level: list[dict]) -> str:
    """Разбивка по уровням — главная новая величина многоуровневой схемы.

    Без неё админ видит общий итог и не понимает, какую его часть создаёт глубина
    цепочки, то есть не может судить, окупается ли она.
    """
    meaningful = [row for row in by_level if row.get('money_kopeks') or row.get('days')]
    if len(meaningful) < 2:
        # Единственный уровень — это обычная одноуровневая программа, и блок
        # только зашумил бы экран.
        return ''

    lines = ['\n<b>По уровням:</b>']
    for row in meaningful:
        lines.append(f'- Уровень {row["level"]}: {_paid_line(row.get("money_kopeks", 0), row.get("days", 0))}')
    return '\n'.join(lines) + '\n'


async def _program_rules_block(db: AsyncSession) -> str:
    """Действующие правила программы.

    В многоуровневой схеме печатать легаси-ключи нельзя: они не управляют ни одним
    начислением, и админ читал бы суммы, которых бот не платит. Описание берётся из
    того же источника, что и расчёт.
    """
    if not settings.is_referral_levels_scheme():
        return (
            '<b>Настройки реферальной системы:</b>\n'
            f'- Минимальное пополнение: {settings.format_price(settings.REFERRAL_MINIMUM_TOPUP_KOPEKS)}\n'
            f'- Бонус за первое пополнение: {settings.format_price(settings.REFERRAL_FIRST_TOPUP_BONUS_KOPEKS)}\n'
            f'- Бонус пригласившему: {settings.format_price(settings.REFERRAL_INVITER_BONUS_KOPEKS)}\n'
            f'- Комиссия с покупок: {settings.REFERRAL_COMMISSION_PERCENT}%'
        )

    from app.services.referral_reward_service import describe_active_levels, describe_referee_bonus

    tariff_names = await _reward_tariff_names(db)
    tier_mode = settings.is_referral_tier_levels()
    header = 'уровни за приглашённых' if tier_mode else 'уровни по цепочке'
    lines = [f'<b>Правила программы (многоуровневая схема, {header}):</b>']
    level_lines = await describe_active_levels(db, tariff_names=tariff_names)
    if level_lines:
        lines.extend(f'- {line}' for line in level_lines)
    else:
        lines.append('- ⚠️ Ни один уровень не настроен — награды не начисляются')

    referee_bonus = await describe_referee_bonus(db, tariff_names=tariff_names)
    if referee_bonus:
        lines.append(f'- Приглашённому: {referee_bonus}')
    if tier_mode:
        # Про глубину здесь писать нечего: цепочка не обходится. Зато admin
        # обязан видеть главное отличие режима — платят одному и по одному правилу.
        lines.append('- Платят только прямому пригласившему, применяется один уровень — старший из достигнутых')
    else:
        lines.append(f'- Глубина цепочки: до {settings.get_referral_max_level_depth()} уровней')
    return '\n'.join(lines)


async def _reward_tariff_names(db: AsyncSession) -> dict[int, str]:
    """Названия тарифов, на которые ссылаются уровни.

    Без них описание обещает «7 дн. подписки», умалчивая, в какой тариф они лягут,
    — а это ровно то, что настраивает админ.
    """
    from sqlalchemy import select as _select

    from app.database.models import Tariff
    from app.services.referral_reward_service import ReferralRewardLevelService

    configs = await ReferralRewardLevelService.get_all(db)
    ids = {cfg.referrer_tariff_id for cfg in configs.values() if cfg.referrer_tariff_id}
    ids |= {cfg.referee_tariff_id for cfg in configs.values() if cfg.referee_tariff_id}
    if not ids:
        return {}

    result = await db.execute(_select(Tariff.id, Tariff.name).where(Tariff.id.in_(ids)))
    return {row.id: row.name for row in result.all()}


@admin_required
@error_handler
async def show_referral_statistics(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    try:
        stats = await get_referral_statistics(db)

        avg_per_referrer = 0
        if stats.get('active_referrers', 0) > 0:
            avg_per_referrer = stats.get('total_paid_kopeks', 0) / stats['active_referrers']

        current_time = format_local_datetime(datetime.now(UTC), '%H:%M:%S')

        text = f"""
🤝 <b>Реферальная статистика</b>

<b>Общие показатели:</b>
- Пользователей с рефералами: {stats.get('users_with_referrals', 0)}
- Активных рефереров: {stats.get('active_referrers', 0)}
- Выплачено всего: {_paid_line(stats.get('total_paid_kopeks', 0), stats.get('total_paid_days', 0))}

<b>За период:</b>
- Сегодня: {_paid_line(stats.get('today_earnings_kopeks', 0), stats.get('today_earnings_days', 0))}
- За неделю: {_paid_line(stats.get('week_earnings_kopeks', 0), stats.get('week_earnings_days', 0))}
- За месяц: {_paid_line(stats.get('month_earnings_kopeks', 0), stats.get('month_earnings_days', 0))}

<b>Средние показатели:</b>
- На одного реферера: {settings.format_price(int(avg_per_referrer))}
"""

        text += _levels_breakdown_block(stats.get('by_level') or [])
        text += '\n<b>Топ-5 рефереров:</b>\n'

        top_referrers = stats.get('top_referrers', [])
        if top_referrers:
            for i, referrer in enumerate(top_referrers[:5], 1):
                earned = referrer.get('total_earned_kopeks', 0)
                days = referrer.get('total_earned_days', 0)
                count = referrer.get('referrals_count', 0)
                user_id = referrer.get('user_id', 'N/A')

                if count > 0:
                    text += f'{i}. ID {user_id}: {_paid_line(earned, days)} ({count} реф.)\n'
                else:
                    logger.warning('Реферер имеет рефералов, но есть в топе', user_id=user_id, count=count)
        else:
            text += 'Нет данных\n'

        text += f'\n{await _program_rules_block(db)}'
        text += f"""
- Уведомления: {'✅ Включены' if settings.REFERRAL_NOTIFICATIONS_ENABLED else '❌ Отключены'}

<i>🕐 Обновлено: {current_time}</i>
"""

        keyboard_rows = [
            [types.InlineKeyboardButton(text='🔄 Обновить', callback_data='admin_referrals')],
        ]

        # Кнопка заявок на вывод (если функция включена)
        if settings.is_referral_withdrawal_enabled():
            keyboard_rows.append(
                [types.InlineKeyboardButton(text='💸 Заявки на вывод', callback_data='admin_withdrawal_requests')]
            )

        keyboard_rows.append([types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer('Обновлено')
        except Exception as edit_error:
            if 'message is not modified' in str(edit_error):
                await callback.answer('Данные актуальны')
            else:
                logger.error('Ошибка редактирования сообщения', edit_error=edit_error)
                await callback.answer('Ошибка обновления')

    except Exception as e:
        logger.error('Ошибка в show_referral_statistics', error=e, exc_info=True)

        current_time = format_local_datetime(datetime.now(UTC), '%H:%M:%S')
        text = f"""
🤝 <b>Реферальная статистика</b>

❌ <b>Ошибка загрузки данных</b>

<b>Текущие настройки:</b>
- Минимальное пополнение: {settings.format_price(settings.REFERRAL_MINIMUM_TOPUP_KOPEKS)}
- Бонус за первое пополнение: {settings.format_price(settings.REFERRAL_FIRST_TOPUP_BONUS_KOPEKS)}
- Бонус пригласившему: {settings.format_price(settings.REFERRAL_INVITER_BONUS_KOPEKS)}
- Комиссия с покупок: {settings.REFERRAL_COMMISSION_PERCENT}%

<i>🕐 Время: {current_time}</i>
"""

        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text='🔄 Повторить', callback_data='admin_referrals')],
                [types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_panel')],
            ]
        )

        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except (TelegramAPIError, AttributeError):
            pass
        await callback.answer('Произошла ошибка при загрузке статистики')


@admin_required
@error_handler
async def show_pending_withdrawal_requests(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Показывает список ожидающих заявок на вывод."""
    requests = await referral_withdrawal_service.get_pending_requests(db)

    if not requests:
        text = '📋 <b>Заявки на вывод</b>\n\nНет ожидающих заявок.'

        keyboard_rows = []
        keyboard_rows.append([types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_referrals')])

        await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
        await callback.answer()
        return

    text = f'📋 <b>Заявки на вывод ({len(requests)})</b>\n\n'

    for req in requests[:10]:
        user = await get_user_by_id(db, req.user_id)
        user_name = html.escape(user.full_name) if user and user.full_name else 'Неизвестно'
        user_tg_id = user.telegram_id if user else 'N/A'

        risk_emoji = (
            '🟢' if req.risk_score < 30 else '🟡' if req.risk_score < 50 else '🟠' if req.risk_score < 70 else '🔴'
        )

        text += f'<b>#{req.id}</b> — {user_name} (ID{user_tg_id})\n'
        text += f'💰 {req.amount_kopeks / 100:.0f}₽ | {risk_emoji} Риск: {req.risk_score}/100\n'
        text += f'📅 {format_local_datetime(req.created_at, "%d.%m.%Y %H:%M")}\n\n'

    keyboard_rows = []
    for req in requests[:5]:
        keyboard_rows.append(
            [
                types.InlineKeyboardButton(
                    text=f'#{req.id} — {req.amount_kopeks / 100:.0f}₽', callback_data=f'admin_withdrawal_view_{req.id}'
                )
            ]
        )

    keyboard_rows.append([types.InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_referrals')])

    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
    await callback.answer()


@admin_required
@error_handler
async def view_withdrawal_request(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Показывает детали заявки на вывод."""
    request_id = int(callback.data.split('_')[-1])

    result = await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == request_id))
    request = result.scalar_one_or_none()

    if not request:
        await callback.answer('Заявка не найдена', show_alert=True)
        return

    user = await get_user_by_id(db, request.user_id)
    user_name = html.escape(user.full_name) if user and user.full_name else 'Неизвестно'
    user_tg_id = (user.telegram_id or user.email or f'#{user.id}') if user else 'N/A'

    analysis = json.loads(request.risk_analysis) if request.risk_analysis else {}

    status_text = {
        WithdrawalRequestStatus.PENDING.value: '⏳ Ожидает',
        WithdrawalRequestStatus.APPROVED.value: '✅ Одобрена',
        WithdrawalRequestStatus.REJECTED.value: '❌ Отклонена',
        WithdrawalRequestStatus.COMPLETED.value: '✅ Выполнена',
        WithdrawalRequestStatus.CANCELLED.value: '🚫 Отменена',
    }.get(request.status, request.status)

    text = f"""
📋 <b>Заявка #{request.id}</b>

👤 Пользователь: {user_name}
🆔 ID: <code>{user_tg_id}</code>
💰 Сумма: <b>{request.amount_kopeks / 100:.0f}₽</b>
📊 Статус: {status_text}

💳 <b>Реквизиты:</b>
<code>{html.escape(request.payment_details or '')}</code>

📅 Создана: {format_local_datetime(request.created_at, '%d.%m.%Y %H:%M')}

{referral_withdrawal_service.format_analysis_for_admin(analysis)}
"""

    # В группе (уведомление в админ-чате) — только действия: профиль и список
    # открыли бы админку в общем чате. В личке — полная карточка.
    role = 'group' if callback_from_group(callback) else 'admin'
    keyboard = get_withdrawal_request_keyboard(
        request.id, request.status, user_db_id=user.id if user else None, role=role, navigation=(role == 'admin')
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@admin_required
@error_handler
async def approve_withdrawal_request(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Одобряет заявку на вывод."""
    request_id = int(callback.data.split('_')[-1])

    result = await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == request_id))
    request = result.scalar_one_or_none()

    if not request:
        await callback.answer('Заявка не найдена', show_alert=True)
        return

    success, error = await referral_withdrawal_service.approve_request(db, request_id, db_user.id)

    if success:
        # Уведомляем пользователя (только если есть telegram_id) — тем же текстом, что и из кабинета
        user = await get_user_by_id(db, request.user_id)
        await notify_user_about_withdrawal_status(
            callback.bot,
            user,
            request_id=request.id,
            amount_kopeks=request.amount_kopeks,
            status=WithdrawalRequestStatus.APPROVED.value,
            comment=None,
        )

        await callback.answer('✅ Заявка одобрена, средства списаны с баланса')

        # Обновляем отображение
        await view_withdrawal_request(callback, db_user, db)
    else:
        await callback.answer(f'❌ {error}', show_alert=True)


@admin_required
@error_handler
async def reject_withdrawal_request(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Отклоняет заявку на вывод."""
    request_id = int(callback.data.split('_')[-1])

    result = await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == request_id))
    request = result.scalar_one_or_none()

    if not request:
        await callback.answer('Заявка не найдена', show_alert=True)
        return

    # Отклонение в один тап (работает и в группе, где FSM-ввод причины недоступен):
    # причины нет — человек получает нейтральный текст и кнопку «Поддержка».
    success, _error = await referral_withdrawal_service.reject_request(
        db, request_id, db_user.id, DEFAULT_BOT_REJECT_COMMENT
    )

    if success:
        # Уведомляем пользователя (только если есть telegram_id) — тем же текстом, что и из кабинета
        user = await get_user_by_id(db, request.user_id)
        await notify_user_about_withdrawal_status(
            callback.bot,
            user,
            request_id=request.id,
            amount_kopeks=request.amount_kopeks,
            status=WithdrawalRequestStatus.REJECTED.value,
            comment=None,
        )

        await callback.answer('❌ Заявка отклонена')

        # Обновляем отображение
        await view_withdrawal_request(callback, db_user, db)
    else:
        await callback.answer('❌ Ошибка отклонения', show_alert=True)


@admin_required
@error_handler
async def complete_withdrawal_request(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Отмечает заявку как выполненную (деньги переведены)."""
    request_id = int(callback.data.split('_')[-1])

    result = await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == request_id))
    request = result.scalar_one_or_none()

    if not request:
        await callback.answer('Заявка не найдена', show_alert=True)
        return

    success, _error = await referral_withdrawal_service.complete_request(db, request_id, db_user.id, 'Перевод выполнен')

    if success:
        # Уведомляем пользователя (только если есть telegram_id) — тем же текстом, что и из кабинета
        user = await get_user_by_id(db, request.user_id)
        await notify_user_about_withdrawal_status(
            callback.bot,
            user,
            request_id=request.id,
            amount_kopeks=request.amount_kopeks,
            status=WithdrawalRequestStatus.COMPLETED.value,
            comment=None,
        )

        await callback.answer('✅ Заявка выполнена')

        # Обновляем отображение
        await view_withdrawal_request(callback, db_user, db)
    else:
        await callback.answer('❌ Ошибка выполнения', show_alert=True)


# =============================================================================
# Проверка бонусов по БД
# =============================================================================


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_referral_statistics, F.data == 'admin_referrals')
    # Хендлеры заявок на вывод
    dp.callback_query.register(show_pending_withdrawal_requests, F.data == 'admin_withdrawal_requests')
    dp.callback_query.register(view_withdrawal_request, F.data.startswith('admin_withdrawal_view_'))
    dp.callback_query.register(approve_withdrawal_request, F.data.startswith('admin_withdrawal_approve_'))
    dp.callback_query.register(reject_withdrawal_request, F.data.startswith('admin_withdrawal_reject_'))
    dp.callback_query.register(complete_withdrawal_request, F.data.startswith('admin_withdrawal_complete_'))
