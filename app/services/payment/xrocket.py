"""Mixin с логикой обработки платежей xRocket."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from importlib import import_module
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import PaymentMethod, TransactionType
from app.services.pricing_engine import RenewalPricing, pricing_engine
from app.services.subscription_renewal_service import (
    RenewalPaymentDescriptor,
    SubscriptionRenewalChargeError,
    SubscriptionRenewalPricing,
    SubscriptionRenewalService,
    build_renewal_period_id,
    decode_payment_payload,
    parse_payment_metadata,
)
from app.utils.payment_logger import payment_logger as logger
from app.utils.user_utils import format_referrer_info


xrocket_renewal_service = SubscriptionRenewalService()


def _parse_amount_kopeks_from_payload(payload: str) -> int:
    """Достаёт копейки из payload вида balance_topup_{uid}_{kopeks} / balance_{uid}_{kopeks}."""
    import re as _re

    match = _re.search(r'_(\d+)$', payload or '')
    if match:
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return 0
    return 0


@dataclass(slots=True)
class _XRocketAdminNotificationContext:
    user_id: int
    transaction_id: int
    old_balance: int
    topup_status: str
    referrer_info: str


@dataclass(slots=True)
class _XRocketUserNotificationPayload:
    telegram_id: int
    text: str
    parse_mode: str | None
    reply_markup: Any
    amount_rubles: float
    asset: str


class XRocketPaymentMixin:
    """Mixin, отвечающий за генерацию инвойсов xRocket и обработку webhook."""

    async def create_xrocket_payment(
        self,
        db: AsyncSession,
        user_id: int | None,
        amount_kopeks: int,
        asset: str | None = None,
        description: str = 'Пополнение баланса',
        payload: str | None = None,
    ) -> dict[str, Any] | None:
        """Создаёт invoice в xRocket в выбранном активе.

        Сумма задаётся в рублях (копейках). Конвертация RUB -> asset идёт по
        курсу самого xRocket (Trade API), поэтому пользователь платит ровно
        столько крипты, сколько соответствует запрошенной рублёвой сумме.
        """
        if not getattr(self, 'xrocket_service', None):
            logger.error('xRocket сервис не инициализирован')
            return None

        asset = (asset or settings.XROCKET_DEFAULT_ASSET).upper()

        allowed = settings.get_xrocket_assets()
        if asset not in allowed:
            logger.error('xRocket: актив не разрешён настройками', asset=asset, allowed=allowed)
            return None

        if amount_kopeks <= 0:
            logger.error('xRocket: некорректная сумма', amount_kopeks=amount_kopeks)
            return None

        try:
            amount_rubles = Decimal(amount_kopeks) / Decimal(100)

            rate = await self.xrocket_service.get_fiat_rate(asset, 'RUB')
            if not rate or rate <= 0:
                logger.error('xRocket: не удалось получить курс, платёж отменён', asset=asset)
                return None

            # 1 asset = rate RUB  ->  amount_asset = rubles / rate
            amount_asset = (amount_rubles / Decimal(str(rate))).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )

            min_invoice = await self.xrocket_service.get_min_invoice(asset)
            if min_invoice and float(amount_asset) < min_invoice:
                logger.error(
                    'xRocket: сумма ниже минимальной для актива',
                    asset=asset,
                    amount_asset=float(amount_asset),
                    min_invoice=min_invoice,
                )
                return None

            if amount_asset <= 0:
                logger.error('xRocket: сумма в активе округлилась до нуля', asset=asset)
                return None

            invoice_data = await self.xrocket_service.create_invoice(
                amount=float(amount_asset),
                currency=asset,
                description=description,
                payload=payload or f'balance_topup_{user_id}_{amount_kopeks}',
                expires_in=settings.get_xrocket_invoice_expires_seconds(),
            )

            if not invoice_data:
                logger.error('Ошибка создания xRocket invoice')
                return None

            xrocket_crud = import_module('app.database.crud.xrocket')

            invoice_id = str(invoice_data['id'])
            pay_url = invoice_data.get('link')
            amount_str = format(amount_asset.normalize(), 'f')

            local_payment = await xrocket_crud.create_xrocket_payment(
                db=db,
                user_id=user_id,
                invoice_id=invoice_id,
                amount=amount_str,
                asset=asset,
                amount_kopeks=amount_kopeks,
                fiat_rate=str(rate),
                status=invoice_data.get('status') or 'active',
                description=description,
                payload=payload,
                pay_url=pay_url,
            )

            logger.info(
                'Создан xRocket платеж',
                invoice_id=invoice_id,
                amount_asset=amount_str,
                asset=asset,
                amount_kopeks=amount_kopeks,
                rate=rate,
                user_id=user_id,
            )

            return {
                'local_payment_id': local_payment.id,
                'invoice_id': invoice_id,
                'amount': amount_str,
                'asset': asset,
                'amount_kopeks': amount_kopeks,
                'rate': rate,
                'pay_url': pay_url,
                'status': local_payment.status,
                'created_at': (local_payment.created_at.isoformat() if local_payment.created_at else None),
            }

        except Exception as error:
            logger.error('Ошибка создания xRocket платежа', error=error, exc_info=True)
            return None

    async def process_xrocket_webhook(
        self,
        db: AsyncSession,
        webhook_data: dict[str, Any],
    ) -> bool:
        """Обрабатывает webhook от xRocket и начисляет средства пользователю."""
        try:
            update_type = webhook_data.get('type')

            if update_type != 'invoicePay':
                logger.info('Пропуск xRocket webhook с типом', update_type=update_type)
                return True

            payload = webhook_data.get('data', {}) or {}

            if (payload.get('status') or '').lower() != 'paid':
                logger.info('Пропуск xRocket webhook: инвойс не оплачен', status=payload.get('status'))
                return True

            invoice_id = str(payload.get('id') or '')
            status = 'paid'

            if not invoice_id:
                logger.error('xRocket webhook без invoice_id')
                return False

            xrocket_crud = import_module('app.database.crud.xrocket')
            payment = await xrocket_crud.get_xrocket_payment_by_invoice_id(db, invoice_id)
            if not payment:
                logger.warning(
                    'xRocket платеж не найден в БД: (возвращаем 200 чтобы остановить ретраи)', invoice_id=invoice_id
                )
                return True

            # Lock payment row immediately to prevent concurrent webhook processing (TOCTOU race)
            locked = await xrocket_crud.get_xrocket_payment_by_invoice_id_for_update(db, invoice_id)
            if not locked:
                logger.error('xRocket: не удалось заблокировать платёж', invoice_id=invoice_id)
                return False
            payment = locked

            if payment.status == 'paid':
                logger.info('xRocket платеж уже обработан', invoice_id=invoice_id)
                return True

            paid_at_str = payload.get('paid') or (payload.get('payment') or {}).get('paid')
            if paid_at_str:
                try:
                    paid_at = datetime.fromisoformat(paid_at_str.replace('Z', '+00:00'))
                except Exception:
                    paid_at = datetime.now(UTC)
            else:
                paid_at = datetime.now(UTC)

            # Inline field updates — NO intermediate commit that would release FOR UPDATE lock
            payment.status = status
            payment.updated_at = datetime.now(UTC)
            if status == 'paid' and paid_at:
                payment.paid_at = paid_at
            await db.flush()

            updated_payment = payment

            descriptor = decode_payment_payload(
                getattr(updated_payment, 'payload', '') or '',
                expected_user_id=updated_payment.user_id,
            )

            if descriptor is None:
                inline_payload = payload.get('payload')
                if isinstance(inline_payload, str) and inline_payload:
                    descriptor = decode_payment_payload(
                        inline_payload,
                        expected_user_id=updated_payment.user_id,
                    )

            if descriptor is None:
                metadata = payload.get('metadata')
                if isinstance(metadata, dict) and metadata:
                    descriptor = parse_payment_metadata(
                        metadata,
                        expected_user_id=updated_payment.user_id,
                    )
            if descriptor:
                renewal_handled = await self._process_xrocket_subscription_renewal_payment(
                    db,
                    updated_payment,
                    descriptor,
                    xrocket_crud,
                )
                if renewal_handled:
                    return True

            # FOR UPDATE lock already acquired above — no need to re-lock

            # --- Guest purchase flow (landing page) ---
            # xRocket stores guest metadata in the payload field (JSON string),
            # not in metadata_json (which doesn't exist on xRocketPayment).
            xr_payload_str = getattr(updated_payment, 'payload', '') or ''
            xr_guest_meta: dict[str, Any] | None = None
            if xr_payload_str:
                try:
                    import json as _json

                    parsed = _json.loads(xr_payload_str)
                    if isinstance(parsed, dict) and parsed.get('purpose') == 'guest_purchase':
                        xr_guest_meta = parsed
                except (ValueError, TypeError):
                    pass

            if xr_guest_meta is not None:
                from app.services.payment.common import try_fulfill_guest_purchase

                guest_result = await try_fulfill_guest_purchase(
                    db,
                    metadata=xr_guest_meta,
                    payment_amount_kopeks=int(getattr(updated_payment, 'amount_kopeks', 0) or 0),
                    provider_payment_id=invoice_id,
                    provider_name='xrocket',
                    # Курс крипты может сдвинуться между созданием и оплатой инвойса,
                    # поэтому строгую сверку суммы не включаем.
                    skip_amount_check=True,
                )
                if guest_result is not None:
                    locked.status = 'paid'
                    locked.paid_at = datetime.now(UTC)
                    await db.commit()
                    return True

            if not updated_payment.transaction_id:
                # Начисляем сумму, зафиксированную при создании инвойса.
                # Обратная конвертация крипты в рубли на вебхуке дала бы дрейф курса
                # (и катастрофу для активов вроде BTC, где 1 единица ~ миллионы рублей).
                amount_kopeks = int(getattr(updated_payment, 'amount_kopeks', 0) or 0)

                if amount_kopeks <= 0:
                    # Fallback для старых записей без amount_kopeks: парсим payload
                    parsed = _parse_amount_kopeks_from_payload(getattr(updated_payment, 'payload', '') or '')
                    if parsed:
                        amount_kopeks = parsed
                        logger.warning(
                            'xRocket: amount_kopeks восстановлен из payload',
                            invoice_id=invoice_id,
                            amount_kopeks=amount_kopeks,
                        )

                if amount_kopeks <= 0:
                    logger.error(
                        'xRocket: не удалось определить сумму начисления, платёж не обработан',
                        invoice_id=invoice_id,
                    )
                    return False

                amount_rubles_rounded = amount_kopeks / 100

                payment_service_module = import_module('app.services.payment_service')
                transaction = await payment_service_module.create_transaction(
                    db,
                    user_id=updated_payment.user_id,
                    type=TransactionType.DEPOSIT,
                    amount_kopeks=amount_kopeks,
                    description=(
                        'Пополнение через xRocket '
                        f'({updated_payment.amount} {updated_payment.asset} → {amount_rubles_rounded:.2f}₽)'
                    ),
                    payment_method=PaymentMethod.XROCKET,
                    external_id=invoice_id,
                    is_completed=True,
                    created_at=getattr(updated_payment, 'created_at', None),
                    commit=False,
                )

                await xrocket_crud.link_xrocket_payment_to_transaction(db, invoice_id, transaction.id)

                get_user_by_id = payment_service_module.get_user_by_id
                user = await get_user_by_id(db, updated_payment.user_id)
                if not user:
                    logger.error('Пользователь с ID не найден при пополнении баланса', user_id=updated_payment.user_id)
                    return False

                # Lock user row to prevent concurrent balance race conditions
                from app.database.crud.user import lock_user_for_update

                user = await lock_user_for_update(db, user)

                old_balance = user.balance_kopeks
                was_first_topup = not user.has_made_first_topup

                user.balance_kopeks += amount_kopeks
                user.updated_at = datetime.now(UTC)

                referrer_info = format_referrer_info(user)
                topup_status = '🆕 Первое пополнение' if was_first_topup else '🔄 Пополнение'

                await db.commit()

                # Emit deferred side-effects after atomic commit
                from app.database.crud.transaction import emit_transaction_side_effects

                await emit_transaction_side_effects(
                    db,
                    transaction,
                    amount_kopeks=amount_kopeks,
                    user_id=updated_payment.user_id,
                    type=TransactionType.DEPOSIT,
                    payment_method=PaymentMethod.XROCKET,
                    external_id=invoice_id,
                )

                try:
                    from app.services.referral_service import process_referral_topup

                    await process_referral_topup(
                        db,
                        user.id,
                        amount_kopeks,
                        getattr(self, 'bot', None),
                    )
                except Exception as error:
                    logger.error('Ошибка обработки реферального пополнения xRocket', error=error)

                if was_first_topup and not user.has_made_first_topup and not user.referred_by_id:
                    user.has_made_first_topup = True
                    await db.commit()

                await db.refresh(user)

                admin_notification: _XRocketAdminNotificationContext | None = None
                user_notification: _XRocketUserNotificationPayload | None = None

                bot_instance = getattr(self, 'bot', None)
                if bot_instance:
                    admin_notification = _XRocketAdminNotificationContext(
                        user_id=user.id,
                        transaction_id=transaction.id,
                        old_balance=old_balance,
                        topup_status=topup_status,
                        referrer_info=referrer_info,
                    )

                    try:
                        keyboard = await self.build_topup_success_keyboard(user)
                        message_text = (
                            '✅ <b>Пополнение успешно!</b>\n\n'
                            f'💰 Сумма: {settings.format_price(amount_kopeks)}\n'
                            f'🪙 Платеж: {updated_payment.amount} {updated_payment.asset}\n'
                            f'💱 Курс: 1 {updated_payment.asset} = {updated_payment.fiat_rate or "?"}₽\n'
                            f'🆔 Транзакция: {invoice_id[:8]}...\n\n'
                            'Баланс пополнен автоматически!'
                        )
                        user_notification = _XRocketUserNotificationPayload(
                            telegram_id=user.telegram_id,
                            text=message_text,
                            parse_mode='HTML',
                            reply_markup=keyboard,
                            amount_rubles=amount_rubles_rounded,
                            asset=updated_payment.asset,
                        )
                    except Exception as error:
                        logger.error('Ошибка подготовки уведомления о пополнении xRocket', error=error)

                if admin_notification:
                    await self._deliver_xrocket_admin_topup_notification(admin_notification)

                if user_notification and bot_instance:
                    await self._deliver_xrocket_user_topup_notification(user_notification)

                # Проверяем наличие сохраненной корзины для возврата к оформлению подписки
                try:
                    from app.services.payment.common import send_cart_notification_after_topup

                    await send_cart_notification_after_topup(user, amount_kopeks, db, bot_instance)
                except Exception as error:
                    logger.error(
                        'Ошибка при работе с сохраненной корзиной для пользователя',
                        user_id=user.id,
                        error=error,
                        exc_info=True,
                    )

            return True

        except Exception as error:
            logger.error('Ошибка обработки xRocket webhook', error=error, exc_info=True)
            return False

    async def _process_xrocket_subscription_renewal_payment(
        self,
        db: AsyncSession,
        payment: Any,
        descriptor: RenewalPaymentDescriptor,
        xrocket_crud: Any,
    ) -> bool:
        try:
            payment_service_module = import_module('app.services.payment_service')
            user = await payment_service_module.get_user_by_id(db, payment.user_id)
        except Exception as error:
            logger.error(
                'Не удалось загрузить пользователя для продления через xRocket',
                payment_user_id=getattr(payment, 'user_id', None),
                error=error,
            )
            return False

        if not user:
            logger.error(
                'Пользователь не найден при обработке продления через xRocket',
                payment_user_id=getattr(payment, 'user_id', None),
            )
            return False

        # Find the specific subscription by ID with ownership check
        from app.database.crud.subscription import get_subscription_by_id_for_user

        subscription = await get_subscription_by_id_for_user(db, descriptor.subscription_id, user.id)
        if not subscription:
            logger.warning(
                'Продление через xRocket отклонено: подписка не найдена или не принадлежит пользователю',
                expected_subscription_id=descriptor.subscription_id,
                user_id=user.id,
            )
            return False

        # Validate period_days against allowed periods
        tariff = getattr(subscription, 'tariff', None)
        if tariff and tariff.period_prices:
            allowed_periods = [int(p) for p in tariff.period_prices.keys()]
        else:
            allowed_periods = settings.get_available_renewal_periods()
        if descriptor.period_days not in allowed_periods:
            logger.error(
                'xRocket renewal rejected: period_days not in allowed periods',
                invoice_id=payment.invoice_id,
                period_days=descriptor.period_days,
                allowed_periods=allowed_periods,
            )
            return False

        pricing_model: SubscriptionRenewalPricing | RenewalPricing | None = None
        if descriptor.pricing_snapshot:
            try:
                pricing_model = SubscriptionRenewalPricing.from_payload(descriptor.pricing_snapshot)
            except Exception as error:
                logger.warning(
                    'Не удалось восстановить сохраненную стоимость продления из payload',
                    invoice_id=payment.invoice_id,
                    error=error,
                )

        if pricing_model is None:
            try:
                pricing_model = await pricing_engine.calculate_renewal_price(
                    db,
                    subscription,
                    descriptor.period_days,
                    user=user,
                )
            except Exception as error:
                logger.error(
                    'Не удалось пересчитать стоимость продления для xRocket',
                    invoice_id=payment.invoice_id,
                    error=error,
                )
                return False

            if pricing_model.final_total != descriptor.total_amount_kopeks:
                logger.warning(
                    'Сумма продления через xRocket изменилась',
                    invoice_id=payment.invoice_id,
                    expected_kopeks=descriptor.total_amount_kopeks,
                    actual_kopeks=pricing_model.final_total,
                )
                if pricing_model.final_total > descriptor.total_amount_kopeks:
                    # Price increased since invoice creation — user would be undercharged.
                    # Reject and let the user create a new invoice at the current price.
                    logger.error(
                        'xRocket renewal rejected: recalculated price exceeds agreed amount',
                        invoice_id=payment.invoice_id,
                        agreed_kopeks=descriptor.total_amount_kopeks,
                        recalculated_kopeks=pricing_model.final_total,
                    )
                    return False
                # Price decreased — charge recalculated (lower) amount, user benefits
                logger.info(
                    'xRocket renewal: price decreased, user benefits',
                    invoice_id=payment.invoice_id,
                    agreed_kopeks=descriptor.total_amount_kopeks,
                    recalculated_kopeks=pricing_model.final_total,
                    delta_kopeks=descriptor.total_amount_kopeks - pricing_model.final_total,
                )

        # Override period_days/period_id only on mutable SubscriptionRenewalPricing
        if isinstance(pricing_model, SubscriptionRenewalPricing):
            pricing_model.period_days = descriptor.period_days
            pricing_model.period_id = build_renewal_period_id(descriptor.period_days)

        # When price drops, recalculate balance portion: total minus the fixed external payment
        # This ensures the user isn't overcharged from balance when crypto already covers more
        required_balance = max(
            0,
            pricing_model.final_total - descriptor.missing_amount_kopeks,
        )

        current_balance = getattr(user, 'balance_kopeks', 0)
        if current_balance < required_balance:
            logger.warning(
                'Недостаточно средств на балансе пользователя для завершения продления: нужно , доступно',
                user_id=user.id,
                required_balance=required_balance,
                current_balance=current_balance,
            )
            return False

        description = f'Продление подписки на {descriptor.period_days} дней'

        try:
            result = await xrocket_renewal_service.finalize(
                db,
                user,
                subscription,
                pricing_model,
                charge_balance_amount=required_balance,
                description=description,
                payment_method=PaymentMethod.XROCKET,
            )
        except SubscriptionRenewalChargeError as error:
            logger.error(
                'Списание баланса не выполнено при продлении через xRocket',
                invoice_id=payment.invoice_id,
                error=error,
            )
            return False
        except Exception as error:
            logger.error(
                'Ошибка завершения продления через xRocket', invoice_id=payment.invoice_id, error=error, exc_info=True
            )
            return False

        transaction = result.transaction
        if transaction:
            try:
                await xrocket_crud.link_xrocket_payment_to_transaction(
                    db,
                    payment.invoice_id,
                    transaction.id,
                )
            except Exception as error:
                logger.warning(
                    'Не удалось связать платеж xRocket с транзакцией',
                    invoice_id=payment.invoice_id,
                    transaction_id=transaction.id,
                    error=error,
                )

        external_amount_label = settings.format_price(descriptor.missing_amount_kopeks)
        balance_amount_label = settings.format_price(required_balance)

        logger.info(
            'Подписка продлена через xRocket invoice (внешний платеж , списано с баланса)',
            subscription_id=subscription.id,
            invoice_id=payment.invoice_id,
            external_amount_label=external_amount_label,
            balance_amount_label=balance_amount_label,
        )

        return True

    async def _deliver_xrocket_admin_topup_notification(self, context: _XRocketAdminNotificationContext) -> None:
        """Обертка с одним повтором: транзиентные сбои (сеть Telegram/БД) не должны терять уведомление."""
        import asyncio as _asyncio

        for attempt in (1, 2):
            try:
                await self._deliver_xrocket_admin_topup_notification_once(context)
                return
            except Exception as error:
                if attempt == 1:
                    logger.warning(
                        'Админ-уведомление xRocket не доставлено, повтор через 5 сек', error=str(error)
                    )
                    await _asyncio.sleep(5)
                else:
                    logger.error(
                        'Админ-уведомление xRocket не доставлено после повтора', error=str(error), exc_info=True
                    )

    async def _deliver_xrocket_admin_topup_notification_once(self, context: _XRocketAdminNotificationContext) -> None:
        bot_instance = getattr(self, 'bot', None)
        if not bot_instance:
            return

        try:
            from app.database.crud.transaction import get_transaction_by_id
            from app.database.crud.user import get_user_by_id
            from app.services.admin_notification_service import AdminNotificationService
        except Exception as error:
            logger.error(
                'Не удалось импортировать зависимости для админ-уведомления xRocket', error=error, exc_info=True
            )
            return

        async with AsyncSessionLocal() as session:
            try:
                user = await get_user_by_id(session, context.user_id)
                transaction = await get_transaction_by_id(session, context.transaction_id)
            except Exception as error:
                logger.error('Ошибка загрузки данных для админ-уведомления xRocket', error=error, exc_info=True)
                await session.rollback()
                return

            if not user or not transaction:
                logger.warning(
                    'Пропущена отправка админ-уведомления xRocket: user= transaction',
                    user=bool(user),
                    transaction=bool(transaction),
                )
                return

            notification_service = AdminNotificationService(bot_instance)
            try:
                await notification_service.send_balance_topup_notification(
                    user,
                    transaction,
                    context.old_balance,
                    topup_status=context.topup_status,
                    referrer_info=context.referrer_info,
                    subscription=getattr(user, 'subscription', None),
                    promo_group=getattr(user, 'promo_group', None),
                    db=session,
                )
            except Exception as error:
                logger.error('Ошибка отправки админ-уведомления о пополнении xRocket', error=error, exc_info=True)
                raise

    async def _deliver_xrocket_user_topup_notification(self, payload: _XRocketUserNotificationPayload) -> None:
        bot_instance = getattr(self, 'bot', None)
        if not bot_instance:
            return

        # Skip email-only users (no telegram_id)
        if not payload.telegram_id:
            logger.info('Пропуск Telegram-уведомления о пополнении xRocket для email-пользователя')
            return

        try:
            await bot_instance.send_message(
                payload.telegram_id,
                payload.text,
                parse_mode=payload.parse_mode,
                reply_markup=payload.reply_markup,
            )
            logger.info(
                'Отправлено уведомление пользователю о пополнении',
                telegram_id=payload.telegram_id,
                amount_rubles=f'{payload.amount_rubles:.2f}',
                asset=payload.asset,
            )
        except Exception as error:
            logger.error('Ошибка отправки уведомления о пополнении xRocket', error=error)

    async def get_xrocket_payment_status(
        self,
        db: AsyncSession,
        local_payment_id: int,
    ) -> dict[str, Any] | None:
        """Запрашивает актуальный статус xRocket invoice и синхронизирует его."""

        xrocket_crud = import_module('app.database.crud.xrocket')
        payment = await xrocket_crud.get_xrocket_payment_by_id(db, local_payment_id)
        if not payment:
            logger.warning('xRocket платеж не найден', local_payment_id=local_payment_id)
            return None

        if not self.xrocket_service:
            logger.warning('xRocket сервис не инициализирован для ручной проверки')
            return {'payment': payment}

        invoice_id = payment.invoice_id
        try:
            remote_invoice = await self.xrocket_service.get_invoice(invoice_id)
        except Exception as error:  # pragma: no cover - network errors
            logger.error('Ошибка запроса статуса xRocket invoice', invoice_id=invoice_id, error=error)
            return {'payment': payment}

        if not remote_invoice:
            logger.info('xRocket invoice не найден через API при ручной проверке', invoice_id=invoice_id)
            refreshed = await xrocket_crud.get_xrocket_payment_by_id(db, local_payment_id)
            return {'payment': refreshed or payment}

        status = (remote_invoice.get('status') or '').lower()
        paid_at_str = remote_invoice.get('paid')
        paid_at = None
        if paid_at_str:
            try:
                paid_at = datetime.fromisoformat(str(paid_at_str).replace('Z', '+00:00'))
            except Exception:  # pragma: no cover - defensive parsing
                paid_at = None

        if status == 'paid':
            webhook_payload = {
                'type': 'invoicePay',
                'data': {
                    'id': remote_invoice.get('id') or invoice_id,
                    'amount': remote_invoice.get('amount') or payment.amount,
                    'currency': remote_invoice.get('currency') or payment.asset,
                    'status': 'paid',
                    'paid': paid_at_str,
                    'payload': remote_invoice.get('payload') or payment.payload,
                    'payment': remote_invoice.get('payment') or {},
                },
            }
            await self.process_xrocket_webhook(db, webhook_payload)
        elif status and status != (payment.status or '').lower():
            await xrocket_crud.update_xrocket_payment_status(
                db,
                invoice_id,
                status,
                paid_at,
            )

        refreshed = await xrocket_crud.get_xrocket_payment_by_id(db, local_payment_id)
        return {'payment': refreshed or payment}
