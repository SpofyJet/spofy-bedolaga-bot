"""Обработчики для простой покупки подписки."""

import html
from typing import Any

import structlog
from aiogram import F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.keyboards.inline import get_happ_download_button_row
from app.localization.texts import get_texts
from app.services.payment_service import PaymentService
from app.services.subscription_purchase_service import SubscriptionPurchaseService
from app.states import SubscriptionStates
from app.utils.decorators import error_handler
from app.utils.pricing_utils import compute_simple_subscription_price
from app.utils.subscription_time import local_days_until
from app.utils.subscription_utils import (
    get_display_subscription_link,
    resolve_simple_subscription_device_limit,
)
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)


async def _reject_classic_checkout_in_tariff_mode(callback: types.CallbackQuery) -> bool:
    """Old simple-purchase buttons must not bypass the tariff renewal entry."""
    await callback.answer('Откройте покупку или продление подписки и выберите тариф', show_alert=True)
    return True


@error_handler
async def start_simple_subscription_purchase(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    """Начинает процесс простой покупки подписки."""
    if await _reject_classic_checkout_in_tariff_mode(callback):
        return
    texts = get_texts(db_user.language)

    if not settings.SIMPLE_SUBSCRIPTION_ENABLED:
        await callback.answer('❌ Простая покупка подписки временно недоступна', show_alert=True)
        return

    if settings.is_multi_tariff_enabled():
        await callback.answer('Используйте выбор тарифа для управления подписками', show_alert=True)
        return

    # Проверка ограничения на покупку/продление подписки
    if db_user.restriction_subscription:
        reason = html.escape(db_user.restriction_reason or 'Действие ограничено администратором')
        support_url = settings.get_support_contact_url()
        keyboard = []
        if support_url:
            keyboard.append([types.InlineKeyboardButton(text='🆘 Обжаловать', url=support_url)])
        keyboard.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription')])

        await callback.message.edit_text(
            f'🚫 <b>Покупка подписки ограничена</b>\n\n{reason}\n\n'
            'Если вы считаете это ошибкой, вы можете обжаловать решение.',
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        )
        await callback.answer()
        return

    # Проверяем, есть ли у пользователя подписка
    from app.database.crud.subscription import get_subscription_by_user_id

    current_subscription = await get_subscription_by_user_id(db, db_user.id)

    device_limit = resolve_simple_subscription_device_limit()

    # При продлении учитываем количество устройств из текущей подписки
    # (независимо от того, включён ли выбор устройств)
    if current_subscription:
        current_device_limit = current_subscription.device_limit or device_limit
        # Используем максимум из текущего и дефолтного
        device_limit = max(device_limit, current_device_limit)

    # Подготовим параметры простой подписки
    subscription_params = {
        'period_days': settings.SIMPLE_SUBSCRIPTION_PERIOD_DAYS,
        'device_limit': device_limit,
        'traffic_limit_gb': settings.SIMPLE_SUBSCRIPTION_TRAFFIC_GB,
        'squad_uuid': settings.SIMPLE_SUBSCRIPTION_SQUAD_UUID,
    }

    # Сохраняем параметры в состояние
    await state.update_data(subscription_params=subscription_params)

    data = await state.get_data()
    resolved_squad_uuid = await _ensure_simple_subscription_squad_uuid(
        db,
        state,
        subscription_params,
        user_id=db_user.id,
        state_data=data,
    )

    price_kopeks, price_breakdown = await _calculate_simple_subscription_price(
        db,
        subscription_params,
        user=db_user,
        resolved_squad_uuid=resolved_squad_uuid,
    )

    period_days = subscription_params['period_days']
    user_balance_kopeks = db_user.balance_kopeks

    logger.warning(
        'SIMPLE_SUBSCRIPTION_DEBUG_START | user=%s | period=%s | base=%s | traffic=%s | devices=%s | servers=%s | discount=%s | total=%s | squads=%s',
        db_user.id,
        period_days,
        price_breakdown.get('base_price', 0),
        price_breakdown.get('traffic_price', 0),
        price_breakdown.get('devices_price', 0),
        price_breakdown.get('servers_price', 0),
        price_breakdown.get('total_discount', 0),
        price_kopeks,
        ','.join(price_breakdown.get('resolved_squad_uuids', []))
        if price_breakdown.get('resolved_squad_uuids')
        else 'none',
    )

    can_pay_from_balance = user_balance_kopeks >= price_kopeks
    logger.warning(
        'SIMPLE_SUBSCRIPTION_DEBUG_START_BALANCE',
        db_user_id=db_user.id,
        user_balance_kopeks=user_balance_kopeks,
        price_kopeks=price_kopeks,
        can_pay_from_balance=can_pay_from_balance,
    )

    # Проверяем, является ли у пользователя текущая подписка активной платной подпиской
    has_active_paid_subscription = False
    trial_notice = ''
    if current_subscription:
        if not current_subscription.is_trial and current_subscription.is_active:
            # Это платная активная подписка - требуем подтверждение
            has_active_paid_subscription = True
        elif current_subscription.is_trial:
            # Это тестовая подписка
            try:
                days_left = local_days_until(current_subscription.end_date)
            except Exception:
                days_left = 0
            key = (
                'SIMPLE_SUBSCRIPTION_TRIAL_NOTICE_ACTIVE'
                if current_subscription.is_active
                else 'SIMPLE_SUBSCRIPTION_TRIAL_NOTICE_TRIAL'
            )
            trial_notice = texts.t(
                key,
                'ℹ️ У вас уже есть триальная подписка. Она истекает через {days} дн.',
            ).format(days=days_left)

    server_label = _get_simple_subscription_server_label(
        texts,
        subscription_params,
        resolved_squad_uuid,
    )
    show_devices = settings.is_devices_selection_enabled()

    message_lines = [
        '⚡ <b>Простая покупка подписки</b>',
        '',
        f'📅 Период: {subscription_params["period_days"]} дней',
    ]

    if show_devices:
        message_lines.append(f'📱 Устройства: {subscription_params["device_limit"]}')

    traffic_limit_gb = subscription_params['traffic_limit_gb']
    traffic_label = 'Безлимит' if traffic_limit_gb == 0 else f'{traffic_limit_gb} ГБ'

    message_lines.extend(
        [
            f'📊 Трафик: {traffic_label}',
            f'🌍 Сервер: {server_label}',
            '',
            f'💰 Стоимость: {settings.format_price(price_kopeks)}',
            f'💳 Ваш баланс: {settings.format_price(user_balance_kopeks)}',
            '',
        ]
    )

    # Если у пользователя уже есть активная платная подписка, требуем подтверждение
    if has_active_paid_subscription:
        # У пользователя уже есть активная платная подписка
        message_lines.append(
            '⚠️ У вас уже есть активная платная подписка. '
            'Покупка простой подписки изменит параметры вашей текущей подписки. '
            'Требуется подтверждение.'
        )
        message_text = '\n'.join(message_lines)

        # Клавиатура с подтверждением
        keyboard_rows = [
            [
                types.InlineKeyboardButton(
                    text='✅ Подтвердить покупку', callback_data='simple_subscription_confirm_purchase'
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
        ]
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    else:
        # У пользователя нет активной платной подписки (или есть только пробная)
        # Показываем стандартный выбор метода оплаты
        if can_pay_from_balance:
            message_lines.append('Вы можете оплатить подписку с баланса или выбрать другой способ оплаты.')
        else:
            message_lines.append('Баланс пока недостаточный для мгновенной оплаты. Выберите подходящий способ оплаты:')

        message_text = '\n'.join(message_lines)

        if trial_notice:
            message_text = f'{trial_notice}\n\n{message_text}'

        methods_keyboard = _get_simple_subscription_payment_keyboard(db_user.language)
        keyboard_rows = []

        if can_pay_from_balance:
            keyboard_rows.append(
                [
                    types.InlineKeyboardButton(
                        text='✅ Оплатить с баланса',
                        callback_data='simple_subscription_pay_with_balance',
                    )
                ]
            )

        keyboard_rows.extend(methods_keyboard.inline_keyboard)

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await callback.message.edit_text(message_text, reply_markup=keyboard, parse_mode='HTML')

    # Устанавливаем соответствующее состояние
    if has_active_paid_subscription:
        await state.set_state(SubscriptionStates.waiting_for_simple_subscription_confirmation)
    else:
        await state.set_state(SubscriptionStates.waiting_for_simple_subscription_payment_method)
    await callback.answer()


async def _calculate_simple_subscription_price(
    db: AsyncSession,
    params: dict,
    *,
    user: User | None = None,
    resolved_squad_uuid: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Рассчитывает цену простой подписки."""

    resolved_uuids = [resolved_squad_uuid] if resolved_squad_uuid else None
    return await compute_simple_subscription_price(
        db,
        params,
        user=user,
        resolved_squad_uuids=resolved_uuids,
    )


def _get_simple_subscription_payment_keyboard(language: str) -> types.InlineKeyboardMarkup:
    """Создает клавиатуру с методами оплаты для простой подписки."""
    texts = get_texts(language)
    keyboard = []

    # Добавляем доступные методы оплаты
    if settings.TELEGRAM_STARS_ENABLED:
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=texts.t('PAYMENT_TELEGRAM_STARS', '⭐ Telegram Stars'),
                    callback_data='simple_subscription_stars',
                )
            ]
        )

    if settings.is_cryptobot_enabled():
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=texts.t('PAYMENT_CRYPTOBOT', 'Криптовалюта (CryptoBot)'),
                    callback_data='simple_subscription_cryptobot',
                )
            ]
        )

    if settings.is_pay2328_enabled():
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=texts.t('PAYMENT_PAY2328', 'Криптовалюта (2328.io)'),
                    callback_data='simple_subscription_pay2328',
                )
            ]
        )

    if settings.is_wata_enabled():
        keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=texts.t('PAYMENT_CARD_WATA', '💳 Банковская карта (WATA)'),
                    callback_data='simple_subscription_wata',
                )
            ]
        )

    # Кнопка назад
    keyboard.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')])

    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def _get_simple_subscription_server_label(
    texts,
    subscription_params: dict[str, Any],
    resolved_squad_uuid: str | None = None,
) -> str:
    """Возвращает локализованное описание выбранного сервера."""

    if subscription_params.get('squad_uuid'):
        return texts.t('SIMPLE_SUBSCRIPTION_SERVER_SELECTED', 'Выбранный')

    if resolved_squad_uuid:
        return texts.t(
            'SIMPLE_SUBSCRIPTION_SERVER_ASSIGNED',
            'Назначен автоматически',
        )

    return texts.t('SIMPLE_SUBSCRIPTION_SERVER_ANY', 'Любой доступный')


async def _ensure_simple_subscription_squad_uuid(
    db: AsyncSession,
    state: FSMContext,
    subscription_params: dict[str, Any],
    *,
    user_id: int | None = None,
    state_data: dict[str, Any] | None = None,
) -> str | None:
    """Определяет UUID сквада для простой подписки."""

    explicit_uuid = subscription_params.get('squad_uuid')
    if explicit_uuid:
        return explicit_uuid

    if state_data is None:
        state_data = await state.get_data()

    resolved_uuid = state_data.get('resolved_squad_uuid')
    if resolved_uuid:
        return resolved_uuid

    try:
        from app.database.crud.server_squad import get_random_active_squad_uuid

        resolved_uuid = await get_random_active_squad_uuid(db)
    except Exception as error:  # pragma: no cover - defensive logging
        logger.error('SIMPLE_SUBSCRIPTION_RANDOM_SQUAD_ERROR', user_id=user_id, error=error)
        return None

    if resolved_uuid:
        await state.update_data(resolved_squad_uuid=resolved_uuid)
        logger.info('SIMPLE_SUBSCRIPTION_RANDOM_SQUAD_ASSIGNED', user_id=user_id, resolved_uuid=resolved_uuid)

    return resolved_uuid


@error_handler
async def handle_simple_subscription_pay_with_balance(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    """Обрабатывает оплату простой подписки с баланса."""
    if await _reject_classic_checkout_in_tariff_mode(callback):
        return
    texts = get_texts(db_user.language)

    data = await state.get_data()
    subscription_params = data.get('subscription_params', {})

    if not subscription_params:
        await callback.answer('❌ Данные подписки устарели. Пожалуйста, начните сначала.', show_alert=True)
        return

    # Проверяем, имеет ли пользователь активную платную подписку
    from app.database.crud.subscription import get_subscription_by_user_id

    current_subscription = await get_subscription_by_user_id(db, db_user.id)

    if current_subscription and not current_subscription.is_trial and current_subscription.is_active:
        # У пользователя есть активная платная подписка - требуем подтверждение
        await callback.answer(
            '⚠️ У вас уже есть активная платная подписка. Пожалуйста, подтвердите покупку.', show_alert=True
        )
        return

    resolved_squad_uuid = await _ensure_simple_subscription_squad_uuid(
        db,
        state,
        subscription_params,
        user_id=db_user.id,
        state_data=data,
    )

    # Lock user BEFORE pricing to prevent TOCTOU
    from app.database.crud.user import lock_user_for_pricing, subtract_user_balance

    db_user = await lock_user_for_pricing(db, db_user.id)

    # Рассчитываем цену подписки (group discounts per-category)
    price_kopeks, price_breakdown = await _calculate_simple_subscription_price(
        db,
        subscription_params,
        user=db_user,
        resolved_squad_uuid=resolved_squad_uuid,
    )

    # PricingEngine already applies promo-offer discount inside calculate_classic_new_subscription_price.
    # Only determine whether to consume the offer (zero it out after use).
    from app.utils.promo_offer import get_user_active_promo_discount_percent

    consume_promo = get_user_active_promo_discount_percent(db_user) > 0

    total_required = price_kopeks
    logger.warning(
        'SIMPLE_SUBSCRIPTION_DEBUG_PAY_BALANCE',
        db_user_id=db_user.id,
        subscription_params=subscription_params['period_days'],
        price_breakdown=price_breakdown.get('base_price', 0),
        price_breakdown_2=price_breakdown.get('traffic_price', 0),
        price_breakdown_3=price_breakdown.get('devices_price', 0),
        price_breakdown_4=price_breakdown.get('servers_price', 0),
        price_breakdown_5=price_breakdown.get('total_discount', 0),
        total_required=total_required,
        getattr=getattr(db_user, 'balance_kopeks', 0),
    )

    # Проверяем баланс пользователя
    user_balance_kopeks = getattr(db_user, 'balance_kopeks', 0)

    if total_required > 0 and user_balance_kopeks < total_required:
        await callback.answer('❌ Недостаточно средств на балансе для оплаты подписки', show_alert=True)
        return

    try:
        # Списываем средства с баланса пользователя
        purchase_description = f'Оплата подписки на {subscription_params["period_days"]} дней'
        success = await subtract_user_balance(
            db,
            db_user,
            price_kopeks,
            purchase_description,
            consume_promo_offer=consume_promo,
            mark_as_paid_subscription=True,
        )

        if not success:
            await callback.answer('❌ Ошибка списания средств с баланса', show_alert=True)
            return

        # Создаём транзакцию для учёта списания
        from app.database.crud.transaction import create_transaction
        from app.database.models import PaymentMethod, TransactionType

        transaction = await create_transaction(
            db,
            user_id=db_user.id,
            type=TransactionType.SUBSCRIPTION_PAYMENT,
            amount_kopeks=price_kopeks,
            description=purchase_description,
            payment_method=PaymentMethod.BALANCE,
        )

        # Проверяем, есть ли у пользователя уже подписка
        from app.database.crud.subscription import extend_subscription, get_subscription_by_user_id

        existing_subscription = await get_subscription_by_user_id(db, db_user.id)

        reset_traffic = settings.RESET_TRAFFIC_ON_PAYMENT or bool(
            existing_subscription and existing_subscription.is_trial
        )
        if existing_subscription:
            # Если подписка уже существует (платная или тестовая), продлеваем её
            # Сохраняем информацию о текущей подписке, особенно является ли она пробной
            was_trial = existing_subscription.is_trial

            subscription = await extend_subscription(
                db=db,
                subscription=existing_subscription,
                days=subscription_params['period_days'],
                traffic_limit_gb=subscription_params['traffic_limit_gb'],
                device_limit=subscription_params['device_limit'],
                connected_squads=[resolved_squad_uuid] if resolved_squad_uuid else None,
                reset_used_traffic=reset_traffic,
            )

            # Если текущая подписка была пробной, и мы обновляем её
            # нужно изменить статус подписки
            if was_trial:
                from app.database.models import SubscriptionStatus

                # Переводим подписку из пробной в активную платную
                subscription.status = SubscriptionStatus.ACTIVE.value
                subscription.is_trial = False

            await db.commit()
            await db.refresh(subscription)
        else:
            # Если подписки нет, создаём новую
            from app.database.crud.subscription import create_paid_subscription

            subscription = await create_paid_subscription(
                db=db,
                user_id=db_user.id,
                duration_days=subscription_params['period_days'],
                traffic_limit_gb=subscription_params['traffic_limit_gb'],
                device_limit=subscription_params['device_limit'],
                connected_squads=[resolved_squad_uuid] if resolved_squad_uuid else [],
                update_server_counters=True,
            )

        if not subscription:
            # Возвращаем средства на баланс в случае ошибки
            from app.services.payment_service import add_user_balance

            await add_user_balance(
                db,
                db_user.id,
                price_kopeks,
                f'Возврат средств за неудавшуюся подписку на {subscription_params["period_days"]} дней',
            )
            await callback.answer('❌ Ошибка создания подписки. Средства возвращены на баланс.', show_alert=True)
            return

        # Обновляем баланс пользователя
        await db.refresh(db_user)

        # Обновляем или создаём ссылку подписки в RemnaWave
        try:
            from app.services.subscription_service import SubscriptionService

            subscription_service = SubscriptionService()
            remnawave_user = await subscription_service.create_remnawave_user(
                db, subscription, reset_traffic=reset_traffic
            )
            if remnawave_user:
                await db.refresh(subscription)
        except Exception as sync_error:
            logger.error(
                'Ошибка синхронизации подписки с RemnaWave для пользователя',
                db_user_id=db_user.id,
                sync_error=sync_error,
                exc_info=True,
            )
            from app.services.remnawave_retry_queue import remnawave_retry_queue

            if hasattr(subscription, 'id') and hasattr(subscription, 'user_id'):
                remnawave_retry_queue.enqueue(
                    subscription_id=subscription.id,
                    user_id=subscription.user_id,
                    action='create',
                )

        # Отправляем уведомление об успешной покупке
        server_label = _get_simple_subscription_server_label(
            texts,
            subscription_params,
            resolved_squad_uuid,
        )
        show_devices = settings.is_devices_selection_enabled()

        success_lines = [
            '✅ <b>Подписка успешно активирована!</b>',
            '',
            f'📅 Период: {subscription_params["period_days"]} дней',
        ]

        if show_devices:
            success_lines.append(f'📱 Устройства: {subscription_params["device_limit"]}')

        success_traffic_gb = subscription_params['traffic_limit_gb']
        success_traffic_label = 'Безлимит' if success_traffic_gb == 0 else f'{success_traffic_gb} ГБ'

        success_lines.extend(
            [
                f'📊 Трафик: {success_traffic_label}',
                f'🌍 Сервер: {server_label}',
                '',
                f'💰 Списано с баланса: {settings.format_price(price_kopeks)}',
                f'💳 Ваш баланс: {settings.format_price(db_user.balance_kopeks)}',
                '',
                "🔗 Для подключения перейдите в раздел 'Подключиться'",
            ]
        )

        success_message = '\n'.join(success_lines)

        connect_mode = settings.CONNECT_BUTTON_MODE
        subscription_link = get_display_subscription_link(subscription)
        connect_button_text = texts.t('CONNECT_BUTTON', '🔗 Подключиться')

        def _fallback_connect_button() -> types.InlineKeyboardButton:
            return types.InlineKeyboardButton(
                text=connect_button_text,
                callback_data='subscription_connect',
                style='success',
            )

        if connect_mode == 'miniapp_subscription':
            if subscription_link:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        web_app=types.WebAppInfo(url=subscription_link),
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        elif connect_mode == 'miniapp_custom':
            custom_url = settings.MINIAPP_CUSTOM_URL
            if custom_url:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        web_app=types.WebAppInfo(url=custom_url),
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        elif connect_mode == 'link':
            if subscription_link:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        url=subscription_link,
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        elif connect_mode == 'happ_cryptolink':
            if subscription_link:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        callback_data='open_subscription_link',
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        else:
            connect_row = [_fallback_connect_button()]

        keyboard_rows = [connect_row]

        happ_row = get_happ_download_button_row(texts)
        if happ_row:
            keyboard_rows.append(happ_row)

        keyboard_rows.append([types.InlineKeyboardButton(text='🏠 В главное меню', callback_data='back_to_menu')])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await callback.message.edit_text(success_message, reply_markup=keyboard, parse_mode='HTML')

        # Отправляем уведомление админам
        try:
            from app.services.admin_notification_service import AdminNotificationService

            notification_service = AdminNotificationService(callback.bot)
            await notification_service.send_subscription_purchase_notification(
                db,
                db_user,
                subscription,
                transaction,
                subscription_params['period_days'],
                False,  # was_trial_conversion
                amount_kopeks=price_kopeks,
                purchase_type='renewal' if existing_subscription else 'first_purchase',
            )
        except Exception as e:
            logger.error('Ошибка отправки уведомления админам о покупке', error=e)

        await state.clear()
        await callback.answer()

        logger.info(
            'Пользователь успешно купил подписку с баланса',
            telegram_id=db_user.telegram_id,
            price_kopeks=price_kopeks / 100,
        )

    except Exception as error:
        logger.error(
            'Ошибка оплаты простой подписки с баланса для пользователя',
            db_user_id=db_user.id,
            error=error,
            exc_info=True,
        )
        await callback.answer(
            '❌ Ошибка оплаты подписки. Попробуйте позже или обратитесь в поддержку.',
            show_alert=True,
        )
        await state.clear()


@error_handler
async def handle_simple_subscription_pay_with_balance_disabled(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    """Показывает уведомление, если баланса недостаточно для прямой оплаты."""
    await callback.answer(
        '❌ Недостаточно средств на балансе. Пополните баланс или выберите другой способ оплаты.',
        show_alert=True,
    )


@error_handler
async def handle_simple_subscription_other_payment_methods(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    """Обрабатывает выбор других способов оплаты."""
    texts = get_texts(db_user.language)

    data = await state.get_data()
    subscription_params = data.get('subscription_params', {})

    if not subscription_params:
        await callback.answer('❌ Данные подписки устарели. Пожалуйста, начните сначала.', show_alert=True)
        return

    resolved_squad_uuid = await _ensure_simple_subscription_squad_uuid(
        db,
        state,
        subscription_params,
        user_id=db_user.id,
        state_data=data,
    )

    # Рассчитываем цену подписки
    price_kopeks, price_breakdown = await _calculate_simple_subscription_price(
        db,
        subscription_params,
        user=db_user,
        resolved_squad_uuid=resolved_squad_uuid,
    )

    user_balance_kopeks = db_user.balance_kopeks
    can_pay_from_balance = user_balance_kopeks >= price_kopeks
    logger.warning(
        'SIMPLE_SUBSCRIPTION_DEBUG_METHODS',
        db_user_id=db_user.id,
        user_balance_kopeks=user_balance_kopeks,
        price_breakdown=price_breakdown.get('base_price', 0),
        price_breakdown_2=price_breakdown.get('traffic_price', 0),
        price_breakdown_3=price_breakdown.get('devices_price', 0),
        price_breakdown_4=price_breakdown.get('servers_price', 0),
        price_breakdown_5=price_breakdown.get('total_discount', 0),
        price_kopeks=price_kopeks,
        can_pay_from_balance=can_pay_from_balance,
    )

    # Отображаем доступные методы оплаты
    server_label = _get_simple_subscription_server_label(
        texts,
        subscription_params,
        resolved_squad_uuid,
    )
    show_devices = settings.is_devices_selection_enabled()

    message_lines = [
        '💳 <b>Оплата подписки</b>',
        '',
        f'📅 Период: {subscription_params["period_days"]} дней',
    ]

    if show_devices:
        message_lines.append(f'📱 Устройства: {subscription_params["device_limit"]}')

    payment_traffic_gb = subscription_params['traffic_limit_gb']
    payment_traffic_label = 'Безлимит' if payment_traffic_gb == 0 else f'{payment_traffic_gb} ГБ'

    message_lines.extend(
        [
            f'📊 Трафик: {payment_traffic_label}',
            f'🌍 Сервер: {server_label}',
            '',
            f'💰 Стоимость: {settings.format_price(price_kopeks)}',
            '',
            (
                'Вы можете оплатить подписку с баланса или выбрать другой способ оплаты:'
                if can_pay_from_balance
                else 'Выберите подходящий способ оплаты:'
            ),
        ]
    )

    message_text = '\n'.join(message_lines)

    base_keyboard = _get_simple_subscription_payment_keyboard(db_user.language)
    keyboard_rows = []

    if can_pay_from_balance:
        keyboard_rows.append(
            [
                types.InlineKeyboardButton(
                    text='✅ Оплатить с баланса', callback_data='simple_subscription_pay_with_balance'
                )
            ]
        )

    keyboard_rows.extend(base_keyboard.inline_keyboard)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await callback.message.edit_text(message_text, reply_markup=keyboard, parse_mode='HTML')

    await callback.answer()


@error_handler
async def handle_simple_subscription_payment_method(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    """Обрабатывает выбор метода оплаты для простой подписки."""
    if await _reject_classic_checkout_in_tariff_mode(callback):
        return
    texts = get_texts(db_user.language)

    data = await state.get_data()
    subscription_params = data.get('subscription_params', {})

    if not subscription_params:
        await callback.answer('❌ Данные подписки устарели. Пожалуйста, начните сначала.', show_alert=True)
        return

    # Проверяем, имеет ли пользователь активную платную подписку
    from app.database.crud.subscription import get_subscription_by_user_id

    current_subscription = await get_subscription_by_user_id(db, db_user.id)

    if current_subscription and not current_subscription.is_trial and current_subscription.is_active:
        # У пользователя есть активная платная подписка - показываем сообщение
        await callback.answer(
            '⚠️ У вас уже есть активная платная подписка. Пожалуйста, подтвердите покупку через главное меню.',
            show_alert=True,
        )
        return

    payment_method = callback.data.replace('simple_subscription_', '')

    try:
        payment_service = PaymentService(callback.bot)
        purchase_service = SubscriptionPurchaseService()

        resolved_squad_uuid = await _ensure_simple_subscription_squad_uuid(
            db,
            state,
            subscription_params,
            user_id=db_user.id,
            state_data=data,
        )

        # Рассчитываем цену подписки (group discounts per-category)
        price_kopeks, _ = await _calculate_simple_subscription_price(
            db,
            subscription_params,
            user=db_user,
            resolved_squad_uuid=resolved_squad_uuid,
        )

        # Apply promo-offer discount on top of group discounts (consistent with balance-pay path)
        from app.services.pricing_engine import PricingEngine
        from app.utils.promo_offer import get_user_active_promo_discount_percent

        offer_pct = get_user_active_promo_discount_percent(db_user)
        if offer_pct > 0:
            price_kopeks = PricingEngine.apply_discount(price_kopeks, offer_pct)

        if payment_method == 'stars':
            # Оплата через Telegram Stars
            order = await purchase_service.create_subscription_order(
                db=db,
                user_id=db_user.id,
                period_days=subscription_params['period_days'],
                device_limit=subscription_params['device_limit'],
                traffic_limit_gb=subscription_params['traffic_limit_gb'],
                squad_uuid=resolved_squad_uuid,
                payment_method='telegram_stars',
                total_price_kopeks=price_kopeks,
            )

            if not order:
                await callback.answer('❌ Не удалось подготовить заказ. Попробуйте позже.', show_alert=True)
                return

            stars_count = settings.rubles_to_stars(settings.kopeks_to_rubles(price_kopeks))

            stars_traffic_gb = subscription_params['traffic_limit_gb']
            stars_traffic_label = 'Безлимит' if stars_traffic_gb == 0 else f'{stars_traffic_gb} ГБ'

            await callback.bot.send_invoice(
                chat_id=callback.from_user.id,
                title=f'Подписка на {subscription_params["period_days"]} дней',
                description=(
                    f'Простая покупка подписки\n'
                    f'Период: {subscription_params["period_days"]} дней\n'
                    f'Устройства: {subscription_params["device_limit"]}\n'
                    f'Трафик: {stars_traffic_label}'
                ),
                payload=(f'simple_sub_{db_user.id}_{order.id}_{subscription_params["period_days"]}'),
                provider_token='',  # Пустой токен для Telegram Stars
                currency='XTR',  # Telegram Stars
                prices=[types.LabeledPrice(label='Подписка', amount=stars_count)],
            )

            await state.clear()
            await callback.answer()

        elif payment_method == 'cryptobot':
            # Оплата через CryptoBot
            if not settings.is_cryptobot_enabled():
                await callback.answer('❌ Оплата через CryptoBot временно недоступна', show_alert=True)
                return

            amount_rubles = price_kopeks / 100
            if amount_rubles < 100 or amount_rubles > 100000:
                await callback.answer(
                    '❌ Сумма должна быть от 100 до 100 000 ₽ для оплаты через CryptoBot',
                    show_alert=True,
                )
                return

            try:
                from app.utils.currency_converter import currency_converter

                usd_rate = await currency_converter.get_usd_to_rub_rate()
            except Exception as rate_error:
                logger.warning('Не удалось получить курс USD', rate_error=rate_error)
                usd_rate = 95.0

            amount_usd = round(amount_rubles / usd_rate, 2)
            if amount_usd < 1:
                await callback.answer(
                    '❌ Минимальная сумма для оплаты через CryptoBot — примерно 1 USD',
                    show_alert=True,
                )
                return
            if amount_usd > 1000:
                await callback.answer(
                    '❌ Максимальная сумма для оплаты через CryptoBot — 1000 USD',
                    show_alert=True,
                )
                return

            payment_service = PaymentService(callback.bot)
            crypto_result = await payment_service.create_cryptobot_payment(
                db=db,
                user_id=db_user.id,
                amount_usd=amount_usd,
                asset=settings.CRYPTOBOT_DEFAULT_ASSET,
                description=settings.get_subscription_payment_description(
                    subscription_params['period_days'],
                    price_kopeks,
                ),
                payload=f'simple_subscription_{db_user.id}_{price_kopeks}',
            )

            if not crypto_result:
                await callback.answer(
                    '❌ Ошибка создания платежа через CryptoBot. Попробуйте позже или обратитесь в поддержку.',
                    show_alert=True,
                )
                return

            payment_url = (
                crypto_result.get('mini_app_invoice_url')
                or crypto_result.get('bot_invoice_url')
                or crypto_result.get('web_app_invoice_url')
            )

            if not payment_url:
                await callback.answer(
                    '❌ Не удалось получить ссылку для оплаты. Обратитесь в поддержку.',
                    show_alert=True,
                )
                return

            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='🪙 Оплатить через CryptoBot',
                            url=payment_url,
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('CHECK_STATUS_BUTTON', '📊 Проверить статус'),
                            callback_data=f'check_simple_cryptobot_{crypto_result["local_payment_id"]}',
                        )
                    ],
                    [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
                ]
            )

            message_text = (
                '🪙 <b>Оплата через CryptoBot</b>\n\n'
                f'💰 Сумма к оплате: {amount_rubles:.0f} ₽\n'
                f'💵 В долларах: {amount_usd:.2f} USD\n'
                f'Актив: {crypto_result["asset"]}\n'
                f'💱 Курс: 1 USD ≈ {usd_rate:.2f} ₽\n'
                f'🆔 ID платежа: {crypto_result["invoice_id"][:8]}...\n\n'
                '📱 <b>Инструкция:</b>\n'
                "1. Нажмите кнопку 'Оплатить через CryptoBot'\n"
                '2. Выберите актив и следуйте подсказкам\n'
                '3. Подтвердите перевод\n'
                '4. Средства зачислятся автоматически\n\n'
                f'❓ Если возникнут проблемы, обратитесь в {settings.get_support_contact_display_html()}'
            )

            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard,
                parse_mode='HTML',
            )

            await state.clear()
            await callback.answer()
            return

        elif payment_method == 'pay2328':
            if not settings.is_pay2328_enabled():
                await callback.answer('❌ Оплата через 2328.io временно недоступна', show_alert=True)
                return

            amount_rubles = price_kopeks / 100
            if amount_rubles < 100 or amount_rubles > 100000:
                await callback.answer(
                    '❌ Сумма должна быть от 100 до 100 000 ₽ для оплаты через 2328.io',
                    show_alert=True,
                )
                return

            pay2328_result = await payment_service.create_pay2328_payment(
                db=db,
                user_id=db_user.id,
                amount_kopeks=price_kopeks,
                description=settings.get_subscription_payment_description(
                    subscription_params['period_days'],
                    price_kopeks,
                ),
                language=db_user.language,
            )

            if not pay2328_result:
                await callback.answer(
                    '❌ Ошибка создания платежа 2328.io. Попробуйте позже или обратитесь в поддержку.',
                    show_alert=True,
                )
                return

            payment_url = pay2328_result.get('payment_url')
            if not payment_url:
                await callback.answer(
                    '❌ Не удалось получить ссылку для оплаты 2328.io. Обратитесь в поддержку.',
                    show_alert=True,
                )
                return

            local_payment_id = pay2328_result.get('local_payment_id')
            payer_amount = pay2328_result.get('payer_amount')
            payer_currency = pay2328_result.get('payer_currency')
            discount_percent = pay2328_result.get('discount_percent')

            markup_percent = None
            if discount_percent is not None:
                try:
                    markup_percent = -int(discount_percent)
                except (TypeError, ValueError):
                    markup_percent = None

            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='🪙 Оплатить через 2328.io',
                            url=payment_url,
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('CHECK_STATUS_BUTTON', '📊 Проверить статус'),
                            callback_data=f'check_simple_pay2328_{local_payment_id}',
                        )
                    ],
                    [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
                ]
            )

            message_lines = [
                '🪙 <b>Оплата через 2328.io</b>',
                '',
                f'💰 Сумма: {settings.format_price(price_kopeks)}',
            ]

            if payer_amount and payer_currency:
                message_lines.append(f'К оплате: {payer_amount} {payer_currency}')
                try:
                    payer_amount_float = float(payer_amount)
                    if payer_amount_float > 0:
                        rub_per_currency = amount_rubles / payer_amount_float
                        message_lines.append(f'💱 Курс: 1 {payer_currency} ≈ {rub_per_currency:.2f} ₽')
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

            if markup_percent:
                sign = '+' if markup_percent > 0 else ''
                message_lines.append(f'📈 Наценка: {sign}{markup_percent}%')

            message_lines.extend(
                [
                    '',
                    '📱 <b>Инструкция:</b>',
                    "1. Нажмите кнопку 'Оплатить через 2328.io'",
                    '2. Следуйте подсказкам на странице оплаты',
                    '3. Подтвердите перевод',
                    '4. Средства зачислятся автоматически',
                    '',
                    f'❓ Если возникнут проблемы, обратитесь в {settings.get_support_contact_display_html()}',
                ]
            )

            await callback.message.edit_text(
                '\n'.join(message_lines),
                reply_markup=keyboard,
                parse_mode='HTML',
            )

            await state.clear()
            await callback.answer()
            return

        elif payment_method == 'wata':
            # Оплата через WATA
            if not settings.is_wata_enabled():
                await callback.answer('❌ Оплата через WATA временно недоступна', show_alert=True)
                return
            if price_kopeks < settings.WATA_MIN_AMOUNT_KOPEKS or price_kopeks > settings.WATA_MAX_AMOUNT_KOPEKS:
                await callback.answer(
                    f'❌ Сумма для WATA должна быть между {settings.format_price(settings.WATA_MIN_AMOUNT_KOPEKS)} и {settings.format_price(settings.WATA_MAX_AMOUNT_KOPEKS)}.',
                    show_alert=True,
                )
                return

            payment_service = PaymentService(callback.bot)
            try:
                wata_result = await payment_service.create_wata_payment(
                    db=db,
                    user_id=db_user.id,
                    amount_kopeks=price_kopeks,
                    description=settings.get_subscription_payment_description(
                        subscription_params['period_days'],
                        price_kopeks,
                    ),
                    language=db_user.language,
                )
            except Exception as error:
                logger.error('Ошибка создания WATA платежа', error=error)
                wata_result = None

            if not wata_result or not wata_result.get('payment_url'):
                await callback.answer(
                    texts.t(
                        'WATA_PAYMENT_ERROR',
                        '❌ Ошибка создания платежа WATA. Попробуйте позже или обратитесь в поддержку.',
                    ),
                    show_alert=True,
                )
                return

            payment_url = wata_result['payment_url']
            payment_link_id = wata_result.get('payment_link_id')
            local_payment_id = wata_result.get('local_payment_id')

            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('WATA_PAY_BUTTON', '💳 Оплатить через WATA'),
                            url=payment_url,
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('CHECK_STATUS_BUTTON', '📊 Проверить статус'),
                            callback_data=f'check_simple_wata_{local_payment_id}',
                        )
                    ],
                    [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
                ]
            )

            message_template = texts.t(
                'WATA_PAYMENT_INSTRUCTIONS',
                (
                    '💳 <b>Оплата через WATA</b>\n\n'
                    '💰 Сумма: {amount}\n'
                    '🆔 ID платежа: {payment_id}\n\n'
                    '📱 <b>Инструкция:</b>\n'
                    "1. Нажмите кнопку 'Оплатить через WATA'\n"
                    '2. Следуйте подсказкам платежной системы\n'
                    '3. Подтвердите перевод\n'
                    '4. Средства зачислятся автоматически\n\n'
                    '❓ Если возникнут проблемы, обратитесь в {support}'
                ),
            )

            await callback.message.edit_text(
                message_template.format(
                    amount=settings.format_price(price_kopeks),
                    payment_id=payment_link_id,
                    support=settings.get_support_contact_display_html(),
                ),
                reply_markup=keyboard,
                parse_mode='HTML',
            )

            await state.clear()
            await callback.answer()
            return

        else:
            await callback.answer('❌ Неизвестный способ оплаты', show_alert=True)

    except Exception as e:
        logger.error('Ошибка обработки метода оплаты простой подписки', error=e)
        await callback.answer(
            '❌ Ошибка обработки запроса. Попробуйте позже или обратитесь в поддержку.', show_alert=True
        )
        await state.clear()


@error_handler
async def check_simple_cryptobot_payment_status(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    try:
        local_payment_id = int(callback.data.rsplit('_', 1)[-1])
    except (ValueError, IndexError):
        await callback.answer('❌ Некорректный идентификатор платежа', show_alert=True)
        return

    from app.database.crud.cryptobot import get_cryptobot_payment_by_id

    payment = await get_cryptobot_payment_by_id(db, local_payment_id)
    if not payment or payment.user_id != db_user.id:
        await callback.answer('❌ Платеж не найден', show_alert=True)
        return

    status_labels = {
        'active': ('⏳', 'Ожидает оплаты'),
        'paid': ('✅', 'Оплачен'),
        'expired': ('❌', 'Истек'),
    }
    emoji, status_text = status_labels.get(payment.status, ('❓', 'Неизвестно'))

    language = settings.DEFAULT_LANGUAGE
    try:
        from app.services.payment_service import get_user_by_id as fetch_user_by_id

        user = await fetch_user_by_id(db, payment.user_id)
        if user and getattr(user, 'language', None):
            language = user.language
    except Exception as error:
        logger.debug('Не удалось получить пользователя для CryptoBot статуса', error=error)

    texts = get_texts(language)
    message_lines = [
        '🪙 <b>Статус платежа CryptoBot</b>',
        '',
        f'🆔 ID: {payment.invoice_id}',
        f'💰 Сумма: {payment.amount} {payment.asset}',
        f'📊 Статус: {emoji} {status_text}',
        f'📅 Создан: {format_local_datetime(payment.created_at, "%d.%m.%Y %H:%M") if payment.created_at else "—"}',
    ]

    if payment.status == 'paid':
        message_lines.append('\n✅ Платеж подтвержден. Средства уже зачислены.')
    elif payment.status == 'active':
        message_lines.append('\n⏳ Платеж еще ожидает подтверждения. Оплатите счет и проверьте статус позже.')

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('CHECK_STATUS_BUTTON', '📊 Проверить статус'),
                    callback_data=f'check_simple_cryptobot_{local_payment_id}',
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
        ]
    )

    await callback.answer()
    await callback.message.edit_text(
        '\n'.join(message_lines),
        reply_markup=keyboard,
        parse_mode='HTML',
    )


@error_handler
async def check_simple_pay2328_payment_status(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    try:
        local_payment_id = int(callback.data.rsplit('_', 1)[-1])
    except (ValueError, IndexError):
        await callback.answer('❌ Некорректный идентификатор платежа', show_alert=True)
        return

    from app.database.crud.pay2328 import get_pay2328_payment_by_id

    payment = await get_pay2328_payment_by_id(db, local_payment_id)
    if not payment or payment.user_id != db_user.id:
        await callback.answer('❌ Платеж не найден', show_alert=True)
        return

    status_labels = {
        'check': ('⏳', 'Ожидает оплаты'),
        'paid': ('✅', 'Оплачен'),
        'paid_over': ('✅', 'Оплачен (переплата)'),
        'overpaid': ('✅', 'Оплачен (переплата)'),
        'underpaid': ('⚠️', 'Неверная сумма'),
        'underpaid_check': ('⌛', 'Недостаточная сумма, ожидаем доплату'),
        'cancel': ('❌', 'Отменен'),
        'awaiting_confirmation': ('⌛', 'Ожидает подтверждения'),
        'aml_lock': ('⚠️', 'Проверяется'),
    }

    emoji, status_text = status_labels.get(payment.status, ('❓', 'Неизвестно'))

    language = settings.DEFAULT_LANGUAGE
    try:
        from app.services.payment_service import get_user_by_id as fetch_user_by_id

        user = await fetch_user_by_id(db, payment.user_id)
        if user and getattr(user, 'language', None):
            language = user.language
    except Exception as error:
        logger.debug('Не удалось получить пользователя для 2328.io статуса', error=error)

    texts = get_texts(language)

    message_lines = [
        'Статус платежа 2328.io:',
        '',
        f'🆔 UUID: {payment.uuid[:8]}...',
        f'💰 Сумма: {settings.format_price(payment.amount_kopeks)}',
        f'📊 Статус: {emoji} {status_text}',
        f'📅 Создан: {format_local_datetime(payment.created_at, "%d.%m.%Y %H:%M") if payment.created_at else "—"}',
    ]

    if payment.payer_amount and payment.payer_currency:
        message_lines.append(f'🪙 Оплата: {payment.payer_amount} {payment.payer_currency}')

    if payment.is_paid:
        message_lines.append('\n✅ Платеж успешно завершен! Средства уже зачислены.')
    elif payment.status in {'pending', 'check', 'awaiting_confirmation', 'underpaid_check'}:
        message_lines.append('\n⏳ Платеж еще обрабатывается. Завершите оплату и проверьте статус позже.')
        if payment.payment_url:
            message_lines.append(f'\n🔗 Ссылка на оплату: {payment.payment_url}')
    elif payment.status in {'cancel', 'underpaid'}:
        message_lines.append(
            f'\n❌ Платеж не завершен корректно. Обратитесь в {settings.get_support_contact_display()}'
        )

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('CHECK_STATUS_BUTTON', '📊 Проверить статус'),
                    callback_data=f'check_simple_pay2328_{local_payment_id}',
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
        ]
    )

    await callback.answer()
    await callback.message.edit_text(
        '\n'.join(message_lines),
        reply_markup=keyboard,
        parse_mode='HTML',
    )


@error_handler
async def check_simple_wata_payment_status(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    try:
        local_payment_id = int(callback.data.rsplit('_', 1)[-1])
    except (ValueError, IndexError):
        await callback.answer('❌ Некорректный идентификатор платежа', show_alert=True)
        return

    # Владельца проверяем до запроса к провайдеру: id в callback_data подконтролен клиенту.
    from app.database.crud.wata import get_wata_payment_by_id

    owned_payment = await get_wata_payment_by_id(db, local_payment_id)
    if not owned_payment or owned_payment.user_id != db_user.id:
        await callback.answer('❌ Платеж не найден', show_alert=True)
        return

    payment_service = PaymentService(callback.bot)
    status_info = await payment_service.get_wata_payment_status(db, local_payment_id)

    if not status_info:
        await callback.answer('❌ Платеж не найден', show_alert=True)
        return

    payment = status_info['payment']
    texts = get_texts(settings.DEFAULT_LANGUAGE)

    status_labels = {
        'Opened': ('⏳', texts.t('WATA_STATUS_OPENED', 'Ожидает оплаты')),
        'Closed': ('⌛', texts.t('WATA_STATUS_CLOSED', 'Обрабатывается')),
        'Paid': ('✅', texts.t('WATA_STATUS_PAID', 'Оплачен')),
        'Declined': ('❌', texts.t('WATA_STATUS_DECLINED', 'Отклонен')),
    }
    emoji, status_text = status_labels.get(payment.status, ('❓', texts.t('WATA_STATUS_UNKNOWN', 'Неизвестно')))

    message_lines = [
        texts.t('WATA_STATUS_TITLE', '💳 <b>Статус платежа WATA</b>'),
        '',
        f'🆔 ID: {payment.payment_link_id}',
        f'💰 Сумма: {settings.format_price(payment.amount_kopeks)}',
        f'📊 Статус: {emoji} {status_text}',
        f'📅 Создан: {format_local_datetime(payment.created_at, "%d.%m.%Y %H:%M") if payment.created_at else "—"}',
    ]

    if payment.is_paid:
        message_lines.append('\n✅ Платеж успешно завершен! Средства уже зачислены.')
    elif payment.status in {'Opened', 'Closed'}:
        message_lines.append('\n⏳ Платеж еще не завершен. Завершите оплату и проверьте статус позже.')

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('CHECK_STATUS_BUTTON', '📊 Проверить статус'),
                    callback_data=f'check_simple_wata_{local_payment_id}',
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_purchase')],
        ]
    )

    await callback.answer()
    await callback.message.edit_text(
        '\n'.join(message_lines),
        reply_markup=keyboard,
        parse_mode='HTML',
    )


@error_handler
async def confirm_simple_subscription_purchase(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    """Обрабатывает подтверждение простой покупки подписки при наличии активной платной подписки."""
    if await _reject_classic_checkout_in_tariff_mode(callback):
        return
    texts = get_texts(db_user.language)

    data = await state.get_data()
    subscription_params = data.get('subscription_params', {})

    if not subscription_params:
        await callback.answer('❌ Данные подписки устарели. Пожалуйста, начните сначала.', show_alert=True)
        return

    resolved_squad_uuid = await _ensure_simple_subscription_squad_uuid(
        db,
        state,
        subscription_params,
        user_id=db_user.id,
        state_data=data,
    )

    # Lock user BEFORE pricing to prevent TOCTOU
    from app.database.crud.user import lock_user_for_pricing, subtract_user_balance

    db_user = await lock_user_for_pricing(db, db_user.id)

    # Рассчитываем цену подписки (group discounts per-category)
    price_kopeks, price_breakdown = await _calculate_simple_subscription_price(
        db,
        subscription_params,
        user=db_user,
        resolved_squad_uuid=resolved_squad_uuid,
    )

    # PricingEngine already applies promo-offer discount inside calculate_classic_new_subscription_price.
    # Only determine whether to consume the offer (zero it out after use).
    from app.utils.promo_offer import get_user_active_promo_discount_percent

    consume_promo = get_user_active_promo_discount_percent(db_user) > 0

    total_required = price_kopeks
    logger.warning(
        'SIMPLE_SUBSCRIPTION_DEBUG_CONFIRM',
        db_user_id=db_user.id,
        subscription_params=subscription_params['period_days'],
        price_breakdown=price_breakdown.get('base_price', 0),
        price_breakdown_2=price_breakdown.get('traffic_price', 0),
        price_breakdown_3=price_breakdown.get('devices_price', 0),
        price_breakdown_4=price_breakdown.get('servers_price', 0),
        price_breakdown_5=price_breakdown.get('total_discount', 0),
        total_required=total_required,
        getattr=getattr(db_user, 'balance_kopeks', 0),
    )

    # Проверяем баланс пользователя
    user_balance_kopeks = getattr(db_user, 'balance_kopeks', 0)

    if total_required > 0 and user_balance_kopeks < total_required:
        await callback.answer('❌ Недостаточно средств на балансе для оплаты подписки', show_alert=True)
        return

    try:
        # Списываем средства с баланса пользователя
        purchase_description = f'Оплата подписки на {subscription_params["period_days"]} дней'
        success = await subtract_user_balance(
            db,
            db_user,
            price_kopeks,
            purchase_description,
            consume_promo_offer=consume_promo,
            mark_as_paid_subscription=True,
        )

        if not success:
            await callback.answer('❌ Ошибка списания средств с баланса', show_alert=True)
            return

        # Создаём транзакцию для учёта списания
        from app.database.crud.transaction import create_transaction
        from app.database.models import PaymentMethod, TransactionType

        transaction = await create_transaction(
            db,
            user_id=db_user.id,
            type=TransactionType.SUBSCRIPTION_PAYMENT,
            amount_kopeks=price_kopeks,
            description=purchase_description,
            payment_method=PaymentMethod.BALANCE,
        )

        # Проверяем, есть ли у пользователя уже подписка
        from app.database.crud.subscription import extend_subscription, get_subscription_by_user_id

        existing_subscription = await get_subscription_by_user_id(db, db_user.id)

        reset_traffic = settings.RESET_TRAFFIC_ON_PAYMENT or bool(
            existing_subscription and existing_subscription.is_trial
        )
        if existing_subscription:
            # Если подписка уже существует, продлеваем её
            # Сохраняем информацию о текущей подписке, особенно является ли она пробной
            was_trial = existing_subscription.is_trial

            subscription = await extend_subscription(
                db=db,
                subscription=existing_subscription,
                days=subscription_params['period_days'],
                traffic_limit_gb=subscription_params['traffic_limit_gb'],
                device_limit=subscription_params['device_limit'],
                connected_squads=[resolved_squad_uuid] if resolved_squad_uuid else None,
                reset_used_traffic=reset_traffic,
            )

            # Если текущая подписка была пробной, и мы обновляем её
            # нужно изменить статус подписки
            if was_trial:
                from app.database.models import SubscriptionStatus

                # Переводим подписку из пробной в активную платную
                subscription.status = SubscriptionStatus.ACTIVE.value
                subscription.is_trial = False

            await db.commit()
            await db.refresh(subscription)
        else:
            # Если подписки нет, создаём новую
            from app.database.crud.subscription import create_paid_subscription

            subscription = await create_paid_subscription(
                db=db,
                user_id=db_user.id,
                duration_days=subscription_params['period_days'],
                traffic_limit_gb=subscription_params['traffic_limit_gb'],
                device_limit=subscription_params['device_limit'],
                connected_squads=[resolved_squad_uuid] if resolved_squad_uuid else [],
                update_server_counters=True,
            )

        if not subscription:
            # Возвращаем средства на баланс в случае ошибки
            from app.services.payment_service import add_user_balance

            await add_user_balance(
                db,
                db_user.id,
                price_kopeks,
                f'Возврат средств за неудавшуюся подписку на {subscription_params["period_days"]} дней',
            )
            await callback.answer('❌ Ошибка создания подписки. Средства возвращены на баланс.', show_alert=True)
            return

        # Обновляем баланс пользователя
        await db.refresh(db_user)

        # Обновляем или создаём ссылку подписки в RemnaWave
        try:
            from app.services.subscription_service import SubscriptionService

            subscription_service = SubscriptionService()
            remnawave_user = await subscription_service.create_remnawave_user(
                db, subscription, reset_traffic=reset_traffic
            )
            if remnawave_user:
                await db.refresh(subscription)
        except Exception as sync_error:
            logger.error(
                'Ошибка синхронизации подписки с RemnaWave для пользователя',
                db_user_id=db_user.id,
                sync_error=sync_error,
                exc_info=True,
            )
            from app.services.remnawave_retry_queue import remnawave_retry_queue

            if hasattr(subscription, 'id') and hasattr(subscription, 'user_id'):
                remnawave_retry_queue.enqueue(
                    subscription_id=subscription.id,
                    user_id=subscription.user_id,
                    action='create',
                )

        # Отправляем уведомление об успешной покупке
        server_label = _get_simple_subscription_server_label(
            texts,
            subscription_params,
            resolved_squad_uuid,
        )
        show_devices = settings.is_devices_selection_enabled()

        success_lines = [
            '✅ <b>Подписка успешно активирована!</b>',
            '',
            f'📅 Период: {subscription_params["period_days"]} дней',
        ]

        if show_devices:
            success_lines.append(f'📱 Устройства: {subscription_params["device_limit"]}')

        success_traffic_gb = subscription_params['traffic_limit_gb']
        success_traffic_label = 'Безлимит' if success_traffic_gb == 0 else f'{success_traffic_gb} ГБ'

        success_lines.extend(
            [
                f'📊 Трафик: {success_traffic_label}',
                f'🌍 Сервер: {server_label}',
                '',
                f'💰 Списано с баланса: {settings.format_price(price_kopeks)}',
                f'💳 Ваш баланс: {settings.format_price(db_user.balance_kopeks)}',
                '',
                "🔗 Для подключения перейдите в раздел 'Подключиться'",
            ]
        )

        success_message = '\n'.join(success_lines)

        connect_mode = settings.CONNECT_BUTTON_MODE
        subscription_link = get_display_subscription_link(subscription)
        connect_button_text = texts.t('CONNECT_BUTTON', '🔗 Подключиться')

        def _fallback_connect_button() -> types.InlineKeyboardButton:
            return types.InlineKeyboardButton(
                text=connect_button_text,
                callback_data='subscription_connect',
                style='success',
            )

        if connect_mode == 'miniapp_subscription':
            if subscription_link:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        web_app=types.WebAppInfo(url=subscription_link),
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        elif connect_mode == 'miniapp_custom':
            custom_url = settings.MINIAPP_CUSTOM_URL
            if custom_url:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        web_app=types.WebAppInfo(url=custom_url),
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        elif connect_mode == 'link':
            if subscription_link:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        url=subscription_link,
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        elif connect_mode == 'happ_cryptolink':
            if subscription_link:
                connect_row = [
                    types.InlineKeyboardButton(
                        text=connect_button_text,
                        callback_data='open_subscription_link',
                        style='success',
                    )
                ]
            else:
                connect_row = [_fallback_connect_button()]
        else:
            connect_row = [_fallback_connect_button()]

        keyboard_rows = [connect_row]

        happ_row = get_happ_download_button_row(texts)
        if happ_row:
            keyboard_rows.append(happ_row)

        keyboard_rows.append([types.InlineKeyboardButton(text='🏠 В главное меню', callback_data='back_to_menu')])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await callback.message.edit_text(success_message, reply_markup=keyboard, parse_mode='HTML')

        # Отправляем уведомление админам
        try:
            from app.services.admin_notification_service import AdminNotificationService

            notification_service = AdminNotificationService(callback.bot)
            await notification_service.send_subscription_purchase_notification(
                db,
                db_user,
                subscription,
                transaction,
                subscription_params['period_days'],
                False,  # was_trial_conversion
                amount_kopeks=price_kopeks,
                purchase_type='renewal' if existing_subscription else 'first_purchase',
            )
        except Exception as e:
            logger.error('Ошибка отправки уведомления админам о покупке', error=e)

        await state.clear()
        await callback.answer()

        logger.info(
            'Пользователь успешно купил подписку с баланса',
            telegram_id=db_user.telegram_id,
            price_kopeks=price_kopeks / 100,
        )

    except Exception as error:
        logger.error(
            'Ошибка подтверждения простой подписки с баланса для пользователя',
            db_user_id=db_user.id,
            error=error,
            exc_info=True,
        )
        await callback.answer(
            '❌ Ошибка оплаты подписки. Попробуйте позже или обратитесь в поддержку.',
            show_alert=True,
        )
        await state.clear()


def register_simple_subscription_handlers(dp):
    """Регистрирует обработчики простой покупки подписки."""

    dp.callback_query.register(start_simple_subscription_purchase, F.data == 'simple_subscription_purchase')

    dp.callback_query.register(confirm_simple_subscription_purchase, F.data == 'simple_subscription_confirm_purchase')

    dp.callback_query.register(
        handle_simple_subscription_pay_with_balance, F.data == 'simple_subscription_pay_with_balance'
    )

    dp.callback_query.register(
        handle_simple_subscription_pay_with_balance_disabled, F.data == 'simple_subscription_pay_with_balance_disabled'
    )

    dp.callback_query.register(
        handle_simple_subscription_other_payment_methods, F.data == 'simple_subscription_other_payment_methods'
    )

    dp.callback_query.register(handle_simple_subscription_payment_method, F.data.startswith('simple_subscription_'))

    dp.callback_query.register(check_simple_cryptobot_payment_status, F.data.startswith('check_simple_cryptobot_'))

    dp.callback_query.register(check_simple_pay2328_payment_status, F.data.startswith('check_simple_pay2328_'))

    dp.callback_query.register(check_simple_wata_payment_status, F.data.startswith('check_simple_wata_'))
