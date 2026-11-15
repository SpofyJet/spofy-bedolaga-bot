import structlog
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.subscription import update_subscription_autopay
from app.database.models import User
from app.keyboards.inline import (
    get_autopay_days_keyboard,
    get_autopay_keyboard,
    get_autopay_period_keyboard,
)
from app.localization.texts import get_texts
from app.services.user_cart_service import user_cart_service


logger = structlog.get_logger(__name__)


async def _resolve_subscription(callback, db_user, db, state=None):
    """Resolve subscription — delegates to shared resolve_subscription_from_context."""
    from .common import resolve_subscription_from_context

    return await resolve_subscription_from_context(callback, db_user, db, state)


async def handle_autopay_menu(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    texts = get_texts(db_user.language)
    subscription, _ = await _resolve_subscription(callback, db_user, db, state)
    if not subscription:
        await callback.answer(
            texts.t('SUBSCRIPTION_ACTIVE_REQUIRED', '⚠️ У вас нет активной подписки!'),
            show_alert=True,
        )
        return

    # Суточные подписки имеют свой механизм продления, глобальный autopay не применяется
    try:
        await db.refresh(subscription, ['tariff'])
    except Exception as refresh_error:
        logger.warning('Не удалось подгрузить тариф подписки', subscription_id=subscription.id, error=refresh_error)
    if subscription.tariff and getattr(subscription.tariff, 'is_daily', False):
        await callback.message.edit_text(
            texts.t(
                'AUTOPAY_NOT_AVAILABLE_FOR_DAILY',
                'Автоплатеж недоступен для суточных тарифов. Списание происходит автоматически раз в сутки.',
            ),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')]]
            ),
        )
        await callback.answer()
        return

    status = (
        texts.t('AUTOPAY_STATUS_ENABLED', 'включен')
        if subscription.autopay_enabled
        else texts.t('AUTOPAY_STATUS_DISABLED', 'выключен')
    )
    days = subscription.autopay_days_before

    period_value = getattr(subscription, 'autopay_period_days', None)
    if period_value:
        period_text = texts.t('AUTOPAY_PERIOD_VALUE', '{days} дн.').format(days=period_value)
    else:
        period_text = texts.t('AUTOPAY_PERIOD_DEFAULT_VALUE', 'по умолчанию (самый дешёвый период тарифа)')

    text = texts.t(
        'AUTOPAY_MENU_TEXT',
        (
            '💳 <b>Автоплатеж</b>\n\n'
            '📊 <b>Статус:</b> {status}\n'
            '⏰ <b>Списание за:</b> {days} дн. до окончания\n'
            '📅 <b>Период продления:</b> {period}\n\n'
            'Выберите действие:'
        ),
    ).format(status=status, days=days, period=period_text)

    keyboard = get_autopay_keyboard(db_user.language)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode='HTML',
    )
    await callback.answer()


async def toggle_autopay(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return
    enable = callback.data.startswith('autopay_enable')

    if enable:
        # Trial subscriptions cannot use autopay
        if subscription.is_trial or subscription.is_trial is None:
            texts = get_texts(db_user.language)
            await callback.answer(
                texts.t(
                    'AUTOPAY_NOT_AVAILABLE_TRIAL',
                    'Автоплатеж недоступен для пробных подписок.',
                ),
                show_alert=True,
            )
            return

        # Classic subscriptions cannot use autopay when tariff mode is enabled
        if not subscription.tariff_id:
            texts = get_texts(db_user.language)
            await callback.answer(
                texts.t(
                    'AUTOPAY_NOT_AVAILABLE_CLASSIC',
                    'Автоплатеж недоступен. Для продления необходимо выбрать тариф.',
                ),
                show_alert=True,
            )
            return

    # Суточные подписки имеют свой механизм продления (DailySubscriptionService),
    # глобальный autopay для них запрещён
    if enable:
        try:
            await db.refresh(subscription, ['tariff'])
        except Exception:
            logger.warning('Ignored error in toggle_autopay', exc_info=True)
        if subscription.tariff and getattr(subscription.tariff, 'is_daily', False):
            texts = get_texts(db_user.language)
            await callback.answer(
                texts.t(
                    'AUTOPAY_NOT_AVAILABLE_FOR_DAILY',
                    'Автоплатеж недоступен для суточных тарифов. Списание происходит автоматически раз в сутки.',
                ),
                show_alert=True,
            )
            return

    await update_subscription_autopay(db, subscription, enable)

    texts = get_texts(db_user.language)
    status = texts.t('AUTOPAY_STATUS_ENABLED', 'включен') if enable else texts.t('AUTOPAY_STATUS_DISABLED', 'выключен')
    await callback.answer(texts.t('AUTOPAY_TOGGLE_SUCCESS', '✅ Автоплатеж {status}!').format(status=status))

    try:
        await handle_autopay_menu(callback, db_user, db, state)
    except TelegramBadRequest as e:
        if 'message is not modified' in str(e):
            pass
        else:
            raise


async def show_autopay_days(callback: types.CallbackQuery, db_user: User):
    texts = get_texts(db_user.language)
    await callback.message.edit_text(
        texts.t(
            'AUTOPAY_SELECT_DAYS_PROMPT',
            '⏰ Выберите за сколько дней до окончания списывать средства:',
        ),
        reply_markup=get_autopay_days_keyboard(db_user.language),
    )
    await callback.answer()


async def set_autopay_days(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return
    base_data = callback.data.split(':')[0]
    days = int(base_data.split('_')[2])

    await update_subscription_autopay(db, subscription, subscription.autopay_enabled, days)

    texts = get_texts(db_user.language)
    await callback.answer(texts.t('AUTOPAY_DAYS_SET', '✅ Установлено {days} дней!').format(days=days))

    await handle_autopay_menu(callback, db_user, db, state)


def _get_subscription_renewal_periods(subscription) -> list[int]:
    """Available renewal periods for a subscription: tariff periods (preferred) or global env list."""
    tariff = getattr(subscription, 'tariff', None)
    if tariff:
        periods = tariff.get_available_periods() or []
        if periods:
            return sorted(periods)
    return sorted(settings.get_available_renewal_periods())


async def show_autopay_period(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    """Period picker UI for autopay."""
    texts = get_texts(db_user.language)
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return

    try:
        await db.refresh(subscription, ['tariff'])
    except Exception as refresh_error:
        logger.warning('Не удалось подгрузить тариф подписки', subscription_id=subscription.id, error=refresh_error)

    periods = _get_subscription_renewal_periods(subscription)
    current = getattr(subscription, 'autopay_period_days', None)

    await callback.message.edit_text(
        texts.t(
            'AUTOPAY_SELECT_PERIOD_PROMPT',
            '📅 Выберите период, на который автоплатёж будет продлевать подписку:',
        ),
        reply_markup=get_autopay_period_keyboard(periods, current, db_user.language),
    )
    await callback.answer()


async def set_autopay_period(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    """Handle period selection (autopay_period_<N> or autopay_period_default)."""
    from app.database.crud.subscription import update_subscription_autopay as _update_autopay

    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return

    raw = callback.data.split(':')[0]
    suffix = raw[len('autopay_period_') :] if raw.startswith('autopay_period_') else ''
    texts = get_texts(db_user.language)

    if suffix == 'default':
        await _update_autopay(db, subscription, subscription.autopay_enabled, period_days=None)
        await callback.answer(texts.t('AUTOPAY_PERIOD_SET_DEFAULT', '✅ Используется период по умолчанию.'))
    else:
        try:
            days = int(suffix)
        except ValueError:
            await callback.answer(texts.t('INVALID_REQUEST', 'Invalid request'), show_alert=True)
            return

        try:
            await db.refresh(subscription, ['tariff'])
        except Exception:
            logger.warning('Ignored error in set_autopay_period', exc_info=True)

        available = _get_subscription_renewal_periods(subscription)
        if days not in available:
            await callback.answer(
                texts.t(
                    'AUTOPAY_PERIOD_NOT_AVAILABLE',
                    '❌ Этот период недоступен для данной подписки.',
                ),
                show_alert=True,
            )
            return

        await _update_autopay(db, subscription, subscription.autopay_enabled, period_days=days)
        await callback.answer(texts.t('AUTOPAY_PERIOD_SET', '✅ Период автоплатежа: {days} дн.').format(days=days))

    await handle_autopay_menu(callback, db_user, db, state)


async def handle_sbp_recurring_unavailable(callback: types.CallbackQuery, db_user: User):
    """Кнопки СБП-автопродления в старых сообщениях и рассылках: функции больше нет."""
    texts = get_texts(db_user.language)
    await callback.answer(
        texts.t('SBP_RECURRING_UNAVAILABLE', '⚠️ Автопродление через СБП сейчас недоступно'),
        show_alert=True,
    )


async def handle_subscription_cancel(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    get_texts(db_user.language)

    await state.clear()

    # Multi-tariff safe: delete only the cart for the current subscription
    # to avoid nuking carts belonging to other subscriptions.
    cart_data = await user_cart_service.get_user_cart(db_user.id)
    cart_sub_id = None
    if cart_data:
        try:
            raw = cart_data.get('subscription_id')
            if raw is not None:
                cart_sub_id = int(raw)
        except (TypeError, ValueError):
            pass

    if cart_sub_id is not None:
        await user_cart_service.delete_subscription_cart(db_user.id, cart_sub_id)
        # Clean up global key only if it still references this subscription
        global_cart = await user_cart_service.get_user_cart(db_user.id)
        if global_cart and global_cart.get('subscription_id') is not None:
            try:
                if int(global_cart['subscription_id']) == cart_sub_id:
                    await user_cart_service.delete_global_cart_only(db_user.id)
            except (TypeError, ValueError):
                pass
    else:
        # No subscription_id in cart -- safe to delete the global cart
        await user_cart_service.delete_user_cart(db_user.id)

    from app.handlers.menu import show_main_menu

    await show_main_menu(callback, db_user, db)

    await callback.answer('❌ Покупка отменена')
