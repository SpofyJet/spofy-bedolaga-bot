import html
from decimal import ROUND_HALF_UP, Decimal

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.user import get_user_by_telegram_id
from app.external.telegram_stars import TelegramStarsService
from app.keyboards.inline import get_payment_error_keyboard
from app.localization.loader import DEFAULT_LANGUAGE
from app.localization.texts import Texts, get_texts
from app.services.payment_service import PaymentService


logger = structlog.get_logger(__name__)


def _user_texts(user, texts=None):
    return texts or get_texts(getattr(user, 'language', None) or DEFAULT_LANGUAGE)


async def _answer_credited_to_balance(
    message: types.Message,
    language: str | None,
    texts,
    *,
    reason: str,
    stars_amount: int,
    amount_kopeks: int | None,
) -> None:
    """Честно говорим, куда ушла оплата: на баланс (или на ручную проверку, если не вышло)."""
    from app.keyboards.inline import get_stars_credited_to_balance_keyboard

    if amount_kopeks is None:
        text = texts.t(
            'STARS_PAYMENT_ENROLLMENT_ERROR',
            '❌ Произошла ошибка при зачислении средств. Обратитесь в поддержку, платеж будет проверен вручную.',
        )
    else:
        text = (
            reason
            + '\n\n'
            + texts.t(
                'STARS_PAYMENT_CREDITED_TO_BALANCE',
                '💰 Оплата {stars} ⭐ зачислена на баланс: <b>{amount}</b>. '
                'Её можно потратить на подписку, а если что-то не так — напишите в поддержку.',
            ).format(stars=stars_amount, amount=settings.format_price(amount_kopeks))
        )
    await message.answer(
        text,
        parse_mode='HTML',
        reply_markup=get_stars_credited_to_balance_keyboard(language or DEFAULT_LANGUAGE),
    )


async def _credit_to_balance_and_answer(
    message: types.Message,
    db: AsyncSession,
    user,
    texts,
    *,
    stars_amount: int,
    charge_id: str | None,
    problem: str,
    reason: str,
    details: dict | None = None,
) -> bool:
    """Оплата Stars не применилась — зачисляем на баланс, алертим админов, сообщаем пользователю."""
    from app.services.payment.stars import credit_unapplied_stars_payment

    language = texts.language
    amount_kopeks = await credit_unapplied_stars_payment(
        db,
        user=user,
        stars_amount=stars_amount,
        telegram_payment_charge_id=charge_id,
        problem=problem,
        bot=message.bot,
        details=details,
    )
    await _answer_credited_to_balance(
        message, language, texts, reason=reason, stars_amount=stars_amount, amount_kopeks=amount_kopeks
    )
    return amount_kopeks is not None


async def _handle_wheel_spin_payment(
    message: types.Message,
    db: AsyncSession,
    user,
    stars_amount: int,
    payload: str,
    texts,
    charge_id: str | None = None,
):
    """Обработка Stars платежа для колеса удачи.

    Если спин сделать нельзя (колесо выключено, нет подписки, лимит, нет призов,
    ошибка) — оплата зачисляется на баланс: Telegram звёзды сам не возвращает.
    """
    from app.database.crud.transaction import get_transaction_by_external_id
    from app.database.crud.wheel import (
        get_or_create_wheel_config,
        get_user_spins_today,
        get_wheel_prizes,
        get_wheel_spin_by_charge_id,
    )
    from app.database.models import PaymentMethod
    from app.services.wheel_service import wheel_service

    texts = _user_texts(user, texts)
    user_id = user.id  # после db.rollback() атрибуты пользователя истекают

    async def credit_instead(problem: str, reason: str) -> bool:
        await _credit_to_balance_and_answer(
            message,
            db,
            user,
            texts,
            stars_amount=stars_amount,
            charge_id=charge_id,
            problem=f'Спин колеса за Stars не выполнен: {problem}',
            reason=reason,
        )
        return False

    try:
        # Идемпотентность: Telegram доставляет successful_payment «как минимум один раз».
        # Если спин по этому charge_id уже есть — платёж уже обработан, второй приз не выдаём.
        if charge_id and await get_wheel_spin_by_charge_id(db, charge_id):
            logger.info(
                '🎰 Stars wheel spin already processed (idempotent skip)',
                user_id=user.id,
                charge_id=charge_id,
            )
            return True
        # Повтор платежа, который в первый раз ушёл на баланс, — второй раз не зачисляем
        # и не крутим колесо.
        if charge_id and await get_transaction_by_external_id(db, charge_id, PaymentMethod.TELEGRAM_STARS):
            logger.info('🎰 Stars wheel payment already credited to balance (idempotent skip)', charge_id=charge_id)
            return True

        config = await get_or_create_wheel_config(db)

        if not config.is_enabled:
            return await credit_instead(
                'колесо выключено',
                texts.t('STARS_WHEEL_UNAVAILABLE_REASON', '❌ Колесо удачи сейчас недоступно.'),
            )

        # Проверяем наличие активной подписки
        from app.database.crud.subscription import get_subscription_by_user_id

        if settings.is_multi_tariff_enabled():
            from app.database.crud.subscription import get_active_subscriptions_by_user_id

            active_subs = await get_active_subscriptions_by_user_id(db, user.id)
            # Wheel eligibility: any active non-daily subscription qualifies
            non_daily = [s for s in active_subs if not getattr(s, 'is_daily_tariff', False)]
            eligible = non_daily or active_subs
            subscription = max(eligible, key=lambda s: s.days_left) if eligible else None
        else:
            subscription = await get_subscription_by_user_id(db, user.id)
        if not subscription or not subscription.is_active:
            return await credit_instead(
                'нет активной подписки',
                texts.t('STARS_WHEEL_NO_SUBSCRIPTION_REASON', '❌ Для колеса удачи нужна активная подписка.'),
            )

        # Выполняем спин напрямую (оплата уже прошла через Stars)
        prizes = await get_wheel_prizes(db, config.id, active_only=True)

        if not prizes:
            return await credit_instead(
                'призы не настроены',
                texts.t('STARS_PAYMENT_NOT_APPLIED_REASON', '❌ Не получилось применить оплату.'),
            )

        # Дневной лимит — авторитетная проверка в момент начисления. Проверка на этапе
        # создания инвойса в кабинете совещательная и гоночная. Stars уже оплачены —
        # при достигнутом лимите возвращаем их на баланс, а не глотаем.
        if config.daily_spin_limit > 0:
            spins_today = await get_user_spins_today(db, user.id)
            if spins_today >= config.daily_spin_limit:
                return await credit_instead(
                    'достигнут дневной лимит спинов',
                    texts.t('STARS_WHEEL_DAILY_LIMIT_REASON', '❌ На сегодня лимит спинов исчерпан.'),
                )

        # Рассчитываем стоимость в копейках для статистики
        rubles_amount = TelegramStarsService.calculate_rubles_from_stars(stars_amount)
        payment_value_kopeks = int((rubles_amount * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))

        # Рассчитываем вероятности и выбираем приз
        prizes_with_probs = wheel_service.calculate_prize_probabilities(config, prizes, payment_value_kopeks)
        selected_prize = wheel_service._select_prize(prizes_with_probs)

        # Применяем приз
        wheel_outcome: dict = {}
        generated_promocode = await wheel_service._apply_prize(db, user, selected_prize, config, None, wheel_outcome)

        # Создаем запись спина
        from sqlalchemy.exc import IntegrityError

        from app.database.crud.wheel import create_wheel_spin
        from app.database.models import WheelSpinPaymentType

        promocode_id = None
        if generated_promocode:
            from sqlalchemy import text

            result = await db.execute(
                text('SELECT id FROM promocodes WHERE code = :code'), {'code': generated_promocode}
            )
            row = result.fetchone()
            if row:
                promocode_id = row[0]

        logger.info(
            '🎰 Creating wheel spin',
            user_id=user.id,
            telegram_id=user.telegram_id,
            display_name=selected_prize.display_name,
        )

        try:
            spin = await create_wheel_spin(
                db=db,
                user_id=user.id,
                prize_id=selected_prize.id,
                payment_type=WheelSpinPaymentType.TELEGRAM_STARS.value,
                payment_amount=stars_amount,
                payment_value_kopeks=payment_value_kopeks,
                prize_type=selected_prize.prize_type,
                prize_value=selected_prize.prize_value,
                prize_display_name=selected_prize.display_name,
                prize_value_kopeks=selected_prize.prize_value_kopeks,
                generated_promocode_id=promocode_id,
                is_applied=True,
                telegram_charge_id=charge_id,
            )
        except IntegrityError:
            # A concurrent redelivery raced us to the unique charge_id. Because the
            # prize grant above runs with commit=False, the whole spin is one
            # transaction — rolling back here undoes our duplicate grant entirely.
            await db.rollback()
            logger.info(
                '🎰 Stars wheel spin duplicate charge id (idempotent skip)',
                user_id=user.id,
                charge_id=charge_id,
            )
            return True

        logger.info('🎰 Wheel spin created', spin_id=spin.id, user_id=spin.user_id)

        # Ensure all changes are committed (subscription days, traffic GB, etc.)
        await db.commit()
        await wheel_service._sync_subscription_after_spin(user, selected_prize)

        from app.services.wheel_admin_notifier import notify_admin_about_spin

        notify_admin_about_spin(
            user_id=user.id,
            payment_type=WheelSpinPaymentType.TELEGRAM_STARS.value,
            payment_amount=stars_amount,
            prize_emoji=selected_prize.emoji,
            prize_name=selected_prize.display_name,
            promocode=generated_promocode,
        )

        # Отправляем результат
        prize_message = wheel_service._get_prize_message(selected_prize, generated_promocode, wheel_outcome)

        emoji = selected_prize.emoji or '🎁'
        await message.answer(
            f'🎰 <b>Колесо удачи!</b>\n\n'
            f'{emoji} <b>{html.escape(selected_prize.display_name)}</b>\n\n'
            f'{prize_message}\n\n'
            f'⭐ Потрачено: {stars_amount} Stars',
            parse_mode='HTML',
        )

        logger.info(
            '🎰 Wheel spin via Stars',
            user_id=user.id,
            display_name=selected_prize.display_name,
            stars_amount=stars_amount,
        )
        return True

    except Exception as e:
        logger.error('Ошибка обработки wheel spin payment', error=e, exc_info=True)
        try:
            await db.rollback()
            if charge_id and await get_wheel_spin_by_charge_id(db, charge_id):
                # Спин уже записан (приз выдан) — сломалось что-то после; деньги не теряются.
                return True
            return await credit_instead(
                f'ошибка: {type(e).__name__}',
                texts.t('STARS_PAYMENT_NOT_APPLIED_REASON', '❌ Не получилось применить оплату.'),
            )
        except Exception as credit_error:
            logger.error('Не удалось зачислить оплату спина на баланс', error=credit_error, exc_info=True)
            from app.services.payment_problem_alert import alert_payment_not_applied

            await alert_payment_not_applied(
                message.bot,
                provider='telegram_stars',
                problem='Спин колеса за Stars не выполнен, и зачислить оплату на баланс не удалось',
                user_id=user_id,
                reference=charge_id,
                details={'Stars': stars_amount, 'Ошибка': type(credit_error).__name__},
            )
            await _answer_credited_to_balance(
                message, texts.language, texts, reason='', stars_amount=stars_amount, amount_kopeks=None
            )
            return False


async def _handle_trial_payment(
    message: types.Message,
    db: AsyncSession,
    user,
    stars_amount: int,
    payload: str,
    texts,
    charge_id: str | None = None,
):
    """Обработка Stars платежа для платного триала.

    Оплата и активация коммитятся вместе; если активировать не вышло — оплата
    зачисляется на баланс (идемпотентно по charge_id), а не теряется.
    """
    from app.database.crud.subscription import activate_pending_trial_subscription
    from app.database.crud.transaction import (
        create_transaction,
        emit_transaction_side_effects,
        get_transaction_by_external_id,
    )
    from app.database.models import PaymentMethod, TransactionType
    from app.services.admin_notification_service import AdminNotificationService
    from app.services.subscription_service import SubscriptionService

    texts = _user_texts(user, texts)
    user_id = user.id  # после db.rollback() атрибуты пользователя истекают
    activated = False

    async def credit_instead(problem: str) -> bool:
        await _credit_to_balance_and_answer(
            message,
            db,
            user,
            texts,
            stars_amount=stars_amount,
            charge_id=charge_id,
            problem=f'Пробная подписка за Stars не выдана: {problem}',
            reason=texts.t('STARS_SUBSCRIPTION_NOT_ACTIVATED_REASON', '❌ Не удалось активировать подписку.'),
            details={'Payload': payload},
        )
        return False

    try:
        # Повтор того же платежа (оплата триала или зачисление на баланс уже записаны
        # с external_id = charge_id) — ничего не делаем.
        if charge_id and await get_transaction_by_external_id(db, charge_id, PaymentMethod.TELEGRAM_STARS):
            logger.info('Stars trial payment already processed (idempotent skip)', charge_id=charge_id)
            return True

        # Парсим payload: trial_{subscription_id}
        parts = payload.split('_')
        subscription_id = None
        if len(parts) >= 2:
            try:
                subscription_id = int(parts[1])
            except ValueError:
                subscription_id = None
        if subscription_id is None:
            logger.error('Невалидный trial payload', payload=payload)
            return await credit_instead('неверный payload')

        # Ключ — charge_id: так повтор того же платежа отсекается проверкой выше, а второй
        # оплаченный инвойс за тот же триал не активирует его повторно и уйдёт на баланс.
        trial_external_id = charge_id or f'trial_stars_{subscription_id}'

        # Рассчитываем стоимость в копейках
        rubles_amount = TelegramStarsService.calculate_rubles_from_stars(stars_amount)
        amount_kopeks = int((rubles_amount * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))

        # commit=False: транзакция коммитится атомарно с активацией подписки
        # (activate_pending_trial_subscription делает commit) — без «оплаты без подписки».
        transaction = await create_transaction(
            db=db,
            user_id=user.id,
            type=TransactionType.SUBSCRIPTION_PAYMENT,
            amount_kopeks=amount_kopeks,
            description=f'Оплата пробной подписки через Telegram Stars ({stars_amount} ⭐)',
            payment_method=PaymentMethod.TELEGRAM_STARS,
            external_id=trial_external_id,
            is_completed=True,
            commit=False,
        )

        # Активируем pending триальную подписку
        subscription = await activate_pending_trial_subscription(
            db=db,
            subscription_id=subscription_id,
            user_id=user.id,
        )

        if not subscription:
            logger.error(
                'Не удалось активировать триальную подписку для пользователя',
                subscription_id=subscription_id,
                user_id=user_id,
            )
            await db.rollback()
            return await credit_instead('pending-подписка не найдена')

        activated = True
        await emit_transaction_side_effects(
            db,
            transaction,
            amount_kopeks=amount_kopeks,
            user_id=user.id,
            type=TransactionType.SUBSCRIPTION_PAYMENT,
            payment_method=PaymentMethod.TELEGRAM_STARS,
            external_id=trial_external_id,
            is_completed=True,
            description=transaction.description,
        )

        # Создаем пользователя в RemnaWave
        subscription_service = SubscriptionService()
        try:
            await subscription_service.create_remnawave_user(db, subscription)
        except Exception as rw_error:
            logger.error('Ошибка создания пользователя RemnaWave для триала', rw_error=rw_error)
            # Не откатываем подписку, просто логируем - RemnaWave может быть временно недоступен
            from app.services.remnawave_retry_queue import remnawave_retry_queue

            if hasattr(subscription, 'id') and hasattr(subscription, 'user_id'):
                remnawave_retry_queue.enqueue(
                    subscription_id=subscription.id,
                    user_id=subscription.user_id,
                    action='create',
                )

        await db.commit()
        await db.refresh(user)

        # Отправляем уведомление админам
        try:
            admin_notification_service = AdminNotificationService(message.bot)
            await admin_notification_service.send_trial_activation_notification(
                user=user,
                subscription=subscription,
                paid_amount=amount_kopeks,
                payment_method='Telegram Stars',
            )
        except Exception as admin_error:
            logger.warning('Ошибка отправки уведомления админам о триале', admin_error=admin_error)

        # Отправляем сообщение пользователю
        await message.answer(
            f'🎉 <b>Пробная подписка активирована!</b>\n\n'
            f'⭐ Потрачено: {stars_amount} Stars\n'
            f'📅 Период: {settings.TRIAL_DURATION_DAYS} дней\n'
            f'📱 Устройств: {Texts.format_device_limit(subscription.device_limit)}\n\n'
            f'Используйте меню для подключения к VPN.',
            parse_mode='HTML',
        )

        logger.info(
            '✅ Платный триал активирован через Stars',
            user_id=user.id,
            subscription_id=subscription.id,
            stars_amount=stars_amount,
        )
        return True

    except Exception as e:
        logger.error('Ошибка обработки trial payment', error=e, exc_info=True)
        if activated:
            # Подписка уже выдана — сломалось уведомление/синхронизация, деньги не потеряны.
            return True
        try:
            await db.rollback()
            return await credit_instead(f'ошибка: {type(e).__name__}')
        except Exception as credit_error:
            logger.error('Не удалось зачислить оплату триала на баланс', error=credit_error, exc_info=True)
            from app.services.payment_problem_alert import alert_payment_not_applied

            await alert_payment_not_applied(
                message.bot,
                provider='telegram_stars',
                problem='Пробная подписка за Stars не выдана, и зачислить оплату на баланс не удалось',
                user_id=user_id,
                reference=charge_id,
                details={'Stars': stars_amount, 'Payload': payload},
            )
            await _answer_credited_to_balance(
                message, texts.language, texts, reason='', stars_amount=stars_amount, amount_kopeks=None
            )
            return False


_PURCHASE_TOKEN_RE = __import__('re').compile(r'^[A-Za-z0-9_\-]{10,100}$')


def _gift_purchase_problem(purchase, charge_id: str | None) -> str | None:
    """Why a Stars payment for a gift can't be applied, or None when it can.

    try_fulfill_guest_purchase treats a missing purchase and a purchase already paid by
    another payment as «done», and the buyer would read «успешно оплачена» for money that
    went nowhere. A redelivery of the same charge is fine: it is the payment already applied.
    """
    from app.database.models import GuestPurchaseStatus

    if purchase is None:
        return 'Подарочная покупка за Stars: покупка не найдена'
    settled = {
        GuestPurchaseStatus.PAID.value,
        GuestPurchaseStatus.DELIVERED.value,
        GuestPurchaseStatus.PENDING_ACTIVATION.value,
        GuestPurchaseStatus.FAILED.value,
    }
    if purchase.status in settled and (not charge_id or purchase.payment_id != charge_id):
        return f'Подарочная покупка за Stars: покупка уже в статусе {purchase.status}, второй платёж не применён'
    return None


async def _handle_guest_purchase_payment(
    message: types.Message,
    db: AsyncSession,
    user,
    stars_amount: int,
    payload: str,
    telegram_payment_charge_id: str,
):
    """Обработка Stars платежа для гостевой покупки (подарочная подписка из кабинета)."""
    from app.database.crud.landing import get_purchase_by_token
    from app.services.payment.common import try_fulfill_guest_purchase

    try:
        texts = _user_texts(user)
        not_applied_reason = texts.t('STARS_PAYMENT_NOT_APPLIED_REASON', '❌ Не получилось применить оплату.')

        purchase_token = payload[len('guest_purchase_') :]
        if not purchase_token or not _PURCHASE_TOKEN_RE.match(purchase_token):
            logger.error('Invalid purchase_token format in guest_purchase payload', payload=payload)
            await _credit_to_balance_and_answer(
                message,
                db,
                user,
                texts,
                stars_amount=stars_amount,
                charge_id=telegram_payment_charge_id,
                problem='Подарочная покупка за Stars: неверный формат payload',
                reason=not_applied_reason,
                details={'Payload': payload},
            )
            return

        # Verify Stars amount matches expected price (±5% tolerance for conversion rounding)
        existing = await get_purchase_by_token(db, purchase_token)
        problem = _gift_purchase_problem(existing, telegram_payment_charge_id)
        if problem:
            await _credit_to_balance_and_answer(
                message,
                db,
                user,
                texts,
                stars_amount=stars_amount,
                charge_id=telegram_payment_charge_id,
                problem=problem,
                reason=not_applied_reason,
                details={'Покупка': f'#{existing.id}' if existing else 'не найдена'},
            )
            return
        if existing and existing.amount_kopeks:
            expected_stars = max(1, settings.rubles_to_stars(existing.amount_kopeks / 100))
            tolerance = max(1, round(expected_stars * 0.05))
            if abs(stars_amount - expected_stars) > tolerance:
                logger.error(
                    'Stars amount mismatch for guest purchase',
                    paid_stars=stars_amount,
                    expected_stars=expected_stars,
                    purchase_id=existing.id,
                )
                await _credit_to_balance_and_answer(
                    message,
                    db,
                    user,
                    texts,
                    stars_amount=stars_amount,
                    charge_id=telegram_payment_charge_id,
                    problem='Подарочная покупка за Stars: сумма не совпала, подарок не выдан',
                    reason=not_applied_reason,
                    details={'Покупка': f'#{existing.id}', 'Ожидалось звёзд': expected_stars},
                )
                return

        # Calculate kopeks from stars
        rubles_amount = TelegramStarsService.calculate_rubles_from_stars(stars_amount)
        amount_kopeks = int((rubles_amount * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))

        # Build metadata matching what other providers use
        metadata = {
            'purpose': 'guest_purchase',
            'purchase_token': purchase_token,
        }

        result = await try_fulfill_guest_purchase(
            db,
            metadata=metadata,
            payment_amount_kopeks=amount_kopeks,
            provider_payment_id=telegram_payment_charge_id,
            provider_name='telegram_stars',
            skip_amount_check=True,
        )

        if result is True:
            await message.answer(
                '🎁 <b>Подарочная подписка успешно оплачена!</b>\n\n'
                f'⭐ Потрачено: {stars_amount} Stars\n\n'
                'Подарок будет доставлен получателю.',
                parse_mode='HTML',
            )
            logger.info(
                '✅ Guest purchase fulfilled via Stars',
                user_id=user.id,
                stars_amount=stars_amount,
                purchase_id=existing.id if existing else None,
            )
        else:
            logger.error('try_fulfill_guest_purchase returned None for Stars gift', payload=payload)
            await message.answer(
                '❌ Ошибка обработки платежа. Обратитесь в поддержку.',
                reply_markup=get_payment_error_keyboard(user.language, back_callback='back_to_menu'),
            )

    except Exception as e:
        logger.error('Error handling guest purchase Stars payment', error=e, exc_info=True)
        await message.answer(
            '❌ Произошла ошибка при обработке подарочной подписки. Обратитесь в поддержку.',
        )


async def handle_pre_checkout_query(query: types.PreCheckoutQuery):
    texts = get_texts(DEFAULT_LANGUAGE)

    try:
        logger.info(
            '📋 Pre-checkout query',
            from_user_id=query.from_user.id,
            total_amount=query.total_amount,
            invoice_payload=query.invoice_payload,
        )

        allowed_prefixes = ('balance_', 'admin_stars_test_', 'simple_sub_', 'wheel_spin_', 'trial_', 'guest_purchase_')

        if not query.invoice_payload or not query.invoice_payload.startswith(allowed_prefixes):
            logger.warning('Невалидный payload', invoice_payload=query.invoice_payload)
            await query.answer(
                ok=False,
                error_message=texts.t(
                    'STARS_PRECHECK_INVALID_PAYLOAD',
                    'Ошибка валидации платежа. Попробуйте еще раз.',
                ),
            )
            return

        try:
            from app.database.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                user = await get_user_by_telegram_id(db, query.from_user.id)
                if not user:
                    logger.warning('Пользователь не найден в БД', from_user_id=query.from_user.id)
                    await query.answer(
                        ok=False,
                        error_message=texts.t(
                            'STARS_PRECHECK_USER_NOT_FOUND',
                            'Пользователь не найден. Обратитесь в поддержку.',
                        ),
                    )
                    return
                texts = get_texts(user.language or DEFAULT_LANGUAGE)
        except Exception as db_error:
            logger.error('Ошибка подключения к БД в pre_checkout_query', db_error=db_error)
            await query.answer(
                ok=False,
                error_message=texts.t(
                    'STARS_PRECHECK_TECHNICAL_ERROR',
                    'Техническая ошибка. Попробуйте позже.',
                ),
            )
            return

        await query.answer(ok=True)
        logger.info('✅ Pre-checkout одобрен для пользователя', from_user_id=query.from_user.id)

    except Exception as e:
        logger.error('Ошибка в pre_checkout_query', error=e, exc_info=True)
        await query.answer(
            ok=False,
            error_message=texts.t(
                'STARS_PRECHECK_TECHNICAL_ERROR',
                'Техническая ошибка. Попробуйте позже.',
            ),
        )


async def handle_successful_payment(message: types.Message, db: AsyncSession, state: FSMContext, **kwargs):
    texts = get_texts(DEFAULT_LANGUAGE)

    try:
        payment = message.successful_payment
        user_id = message.from_user.id

        logger.info(
            '💳 Успешный Stars платеж',
            user_id=user_id,
            total_amount=payment.total_amount,
            invoice_payload=payment.invoice_payload,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )

        user = await get_user_by_telegram_id(db, user_id)
        texts = get_texts(user.language if user and user.language else DEFAULT_LANGUAGE)
        # process_stars_payment при ошибке делает rollback — атрибуты user после него истекают.
        user_language = user.language if user else None
        user_db_id = user.id if user else None

        if not user:
            logger.error('Пользователь не найден при обработке Stars платежа', user_id=user_id)
            await message.answer(
                texts.t(
                    'STARS_PAYMENT_USER_NOT_FOUND',
                    '❌ Ошибка: пользователь не найден. Обратитесь в поддержку.',
                )
            )
            return

        # Обработка оплаты спина колеса удачи
        if payment.invoice_payload and payment.invoice_payload.startswith('wheel_spin_'):
            await _handle_wheel_spin_payment(
                message=message,
                db=db,
                user=user,
                stars_amount=payment.total_amount,
                payload=payment.invoice_payload,
                texts=texts,
                charge_id=payment.telegram_payment_charge_id,
            )
            return

        # Обработка оплаты платного триала
        if payment.invoice_payload and payment.invoice_payload.startswith('trial_'):
            await _handle_trial_payment(
                message=message,
                db=db,
                user=user,
                stars_amount=payment.total_amount,
                payload=payment.invoice_payload,
                texts=texts,
                charge_id=payment.telegram_payment_charge_id,
            )
            return

        # Обработка оплаты гостевой покупки (подарочная подписка из кабинета)
        if payment.invoice_payload and payment.invoice_payload.startswith('guest_purchase_'):
            await _handle_guest_purchase_payment(
                message=message,
                db=db,
                user=user,
                stars_amount=payment.total_amount,
                payload=payment.invoice_payload,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            return

        payment_service = PaymentService(message.bot)

        state_data = await state.get_data()
        prompt_message_id = state_data.get('stars_prompt_message_id')
        prompt_chat_id = state_data.get('stars_prompt_chat_id', message.chat.id)
        invoice_message_id = state_data.get('stars_invoice_message_id')
        invoice_chat_id = state_data.get('stars_invoice_chat_id', message.chat.id)

        for chat_id, message_id, label in [
            (prompt_chat_id, prompt_message_id, 'запрос суммы'),
            (invoice_chat_id, invoice_message_id, 'инвойс Stars'),
        ]:
            if message_id:
                try:
                    await message.bot.delete_message(chat_id, message_id)
                except Exception as delete_error:  # pragma: no cover - зависит от прав бота
                    logger.warning(
                        'Не удалось удалить сообщение после оплаты Stars', label=label, delete_error=delete_error
                    )

        success = await payment_service.process_stars_payment(
            db=db,
            user_id=user.id,
            stars_amount=payment.total_amount,
            payload=payment.invoice_payload,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )

        await state.update_data(
            stars_prompt_message_id=None,
            stars_prompt_chat_id=None,
            stars_invoice_message_id=None,
            stars_invoice_chat_id=None,
        )

        if success and (payment.invoice_payload or '').startswith('simple_sub_'):
            from app.database.crud.transaction import get_transaction_by_external_id
            from app.database.models import PaymentMethod, TransactionType

            transaction = await get_transaction_by_external_id(
                db, payment.telegram_payment_charge_id, PaymentMethod.TELEGRAM_STARS
            )
            if transaction is not None and transaction.type == TransactionType.DEPOSIT.value:
                # Подписку выдать не вышло — оплата ушла на баланс (сервис уже оповестил админов).
                await _answer_credited_to_balance(
                    message,
                    user_language,
                    texts,
                    reason=texts.t('STARS_SUBSCRIPTION_NOT_ACTIVATED_REASON', '❌ Не удалось активировать подписку.'),
                    stars_amount=payment.total_amount,
                    amount_kopeks=abs(transaction.amount_kopeks),
                )
                return
            if settings.is_notifications_enabled():
                # Подписка активирована — сообщение «Подписка активирована» уже отправил
                # сервис; «Баланс пополнен» здесь было бы неправдой.
                return

        if success:
            rubles_amount = TelegramStarsService.calculate_rubles_from_stars(payment.total_amount)
            amount_kopeks = int((rubles_amount * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))
            amount_text = settings.format_price(amount_kopeks).replace(' ₽', '')

            keyboard = await payment_service.build_topup_success_keyboard(user)

            transaction_id_short = payment.telegram_payment_charge_id[:8]

            await message.answer(
                texts.t(
                    'STARS_PAYMENT_SUCCESS',
                    '🎉 <b>Платеж успешно обработан!</b>\n\n'
                    '⭐ Потрачено звезд: {stars_spent}\n'
                    '💰 Зачислено на баланс: {amount} ₽\n'
                    '🆔 ID транзакции: {transaction_id}...\n\n'
                    'Спасибо за пополнение! 🚀',
                ).format(
                    stars_spent=payment.total_amount,
                    amount=amount_text,
                    transaction_id=transaction_id_short,
                ),
                parse_mode='HTML',
                reply_markup=keyboard,
            )

            logger.info(
                '✅ Stars платеж успешно обработан',
                user_id=user.id,
                total_amount=payment.total_amount,
                format_price=settings.format_price(amount_kopeks),
            )
        else:
            logger.error('Ошибка обработки Stars платежа для пользователя', user_id=user_db_id)
            from app.keyboards.inline import get_stars_credited_to_balance_keyboard

            await message.answer(
                texts.t(
                    'STARS_PAYMENT_ENROLLMENT_ERROR',
                    '❌ Произошла ошибка при зачислении средств. '
                    'Обратитесь в поддержку, платеж будет проверен вручную.',
                ),
                parse_mode='HTML',
                reply_markup=get_stars_credited_to_balance_keyboard(user_language or DEFAULT_LANGUAGE),
            )

    except Exception as e:
        logger.error('Ошибка в successful_payment', error=e, exc_info=True)
        await message.answer(
            texts.t(
                'STARS_PAYMENT_PROCESSING_ERROR',
                '❌ Техническая ошибка при обработке платежа. Обратитесь в поддержку для решения проблемы.',
            ),
            reply_markup=get_payment_error_keyboard(texts.language, back_callback='menu_balance'),
        )


def register_stars_handlers(dp: Dispatcher):
    dp.pre_checkout_query.register(handle_pre_checkout_query, F.currency == 'XTR')

    dp.message.register(handle_successful_payment, F.successful_payment)

    logger.info('🌟 Зарегистрированы обработчики Telegram Stars платежей')
