"""Mixin with 2328.io payment flow implementation."""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from importlib import import_module
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import (
    PAY2328_CLOSED_STATUSES,
    PAY2328_MANUAL_REVIEW_STATUSES,
    PAY2328_PAID_STATUSES,
    PAY2328_REFUND_STATUSES,
    PaymentMethod,
    TransactionType,
)
from app.services.payment.common import topup_success_text
from app.services.payment_problem_alert import alert_invoice_failed, note_invoice_created
from app.utils.payment_logger import payment_logger as logger
from app.utils.user_utils import format_referrer_info


if TYPE_CHECKING:
    from app.database.models import Pay2328Payment


class Pay2328PaymentMixin:
    """Provides helpers to create and process 2328.io payments."""

    async def create_pay2328_payment(
        self,
        db: AsyncSession,
        user_id: int | None,
        amount_kopeks: int,
        description: str,
        *,
        language: str | None = None,
        return_url: str | None = None,
        success_url: str | None = None,
    ) -> dict[str, Any] | None:
        if not getattr(self, 'pay2328_service', None):
            logger.error('2328.io сервис не инициализирован')
            return None

        if amount_kopeks <= 0:
            logger.error('Сумма 2328.io должна быть положительной', amount_kopeks=amount_kopeks)
            return None

        amount_rubles = amount_kopeks / 100
        amount_str = f'{amount_rubles:.2f}'

        order_id = f'pay2328_{user_id or "guest"}_{int(time.time())}_{secrets.token_hex(3)}'

        markup_percent = settings.get_pay2328_markup_percent()
        discount_percent: int | None = None
        if markup_percent:
            try:
                rounded = int(round(markup_percent))
                if rounded != 0:
                    discount_percent = -rounded
            except (TypeError, ValueError):
                logger.warning('Некорректная наценка 2328.io', markup_percent=markup_percent)

        callback_url = settings.get_pay2328_callback_url()
        if not callback_url:
            logger.error('2328.io: не задан адрес вебхука (PAY2328_CALLBACK_URL или WEBHOOK_URL)')
            return None

        payload: dict[str, Any] = {
            'amount': amount_str,
            'currency': 'RUB',
            'order_id': order_id,
            'ttl_seconds': settings.get_pay2328_lifetime(),
            'url_callback': callback_url,
            'url_return': success_url or return_url or settings.PAY2328_SUCCESS_URL or settings.PAY2328_RETURN_URL,
            'description': description[:500] if description else None,
        }

        to_currency = (settings.PAY2328_DEFAULT_CURRENCY or '').strip()
        network = (settings.PAY2328_DEFAULT_NETWORK or '').strip()
        if to_currency and network:
            payload['to_currency'] = to_currency
            payload['network'] = network

        if discount_percent is not None:
            payload['price_markup'] = -discount_percent

        metadata: dict[str, Any] = {
            'language': language or settings.DEFAULT_LANGUAGE,
            'created_at': datetime.now(UTC).isoformat(),
        }

        try:
            response = await self.pay2328_service.create_payment(payload)  # type: ignore[union-attr]
        except Exception as error:  # pragma: no cover - safety net
            logger.exception('Ошибка создания 2328.io платежа', error=error)
            await alert_invoice_failed(
                getattr(self, 'bot', None),
                provider='2328.io',
                reason=type(error).__name__,
                user_id=user_id,
                amount_kopeks=amount_kopeks,
            )
            return None

        payment_result = response.get('result') if isinstance(response, dict) else None
        if not payment_result:
            logger.error('Некорректный или пустой ответ 2328.io API', response=response)
            await alert_invoice_failed(
                getattr(self, 'bot', None),
                provider='2328.io',
                reason='пустой или некорректный ответ',
                user_id=user_id,
                amount_kopeks=amount_kopeks,
            )
            return None

        note_invoice_created('2328.io')

        uuid = str(payment_result.get('uuid'))
        response_order_id = payment_result.get('order_id')
        if response_order_id:
            order_id = str(response_order_id)

        url = payment_result.get('url')
        status = payment_result.get('payment_status') or 'check'
        payer_amount = payment_result.get('payer_amount')
        payer_currency = payment_result.get('payer_currency')
        exchange_rate = payment_result.get('exchange_rate')

        try:
            exchange_rate_value = float(exchange_rate) if exchange_rate is not None else None
        except (TypeError, ValueError):
            exchange_rate_value = None

        if exchange_rate_value is None and payer_amount:
            try:
                exchange_rate_value = float(payer_amount) / amount_rubles if amount_rubles else None
            except (TypeError, ValueError, ZeroDivisionError):
                exchange_rate_value = None

        expires_at: datetime | None = None
        expires_at_raw = payment_result.get('expires_at')
        if expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(str(expires_at_raw).replace('Z', '+00:00')).astimezone(UTC)
            except ValueError:
                logger.warning('2328.io: некорректный expires_at', expires_at=expires_at_raw)

        pay2328_crud = import_module('app.database.crud.pay2328')

        local_payment = await pay2328_crud.create_pay2328_payment(
            db=db,
            user_id=user_id,
            uuid=uuid,
            order_id=order_id,
            amount=amount_str,
            currency='RUB',
            status=status,
            payer_amount=payer_amount,
            payer_currency=payer_currency,
            exchange_rate=exchange_rate_value,
            discount_percent=discount_percent,
            payment_url=url,
            expires_at=expires_at,
            metadata={'raw_response': payment_result, **metadata},
        )

        logger.info('Создан 2328.io платеж', uuid=uuid, amount_str=amount_str, user_id=user_id)

        return {
            'local_payment_id': local_payment.id,
            'uuid': uuid,
            'order_id': order_id,
            'amount': amount_str,
            'amount_kopeks': amount_kopeks,
            'payment_url': url,
            'status': status,
            'payer_amount': payer_amount,
            'payer_currency': payer_currency,
            'exchange_rate': exchange_rate_value,
            'discount_percent': discount_percent,
        }

    async def _process_pay2328_payload(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
        *,
        metadata_key: str,
    ) -> Pay2328Payment | None:
        if not isinstance(payload, dict):
            logger.error('2328.io webhook payload не является словарём', payload=payload)
            return None

        pay2328_crud = import_module('app.database.crud.pay2328')
        payment_module = import_module('app.services.payment_service')

        uuid = str(payload.get('uuid') or '').strip()
        order_id = str(payload.get('order_id') or '').strip()
        status = payload.get('payment_status') or payload.get('status')

        if not uuid and not order_id:
            logger.error('2328.io webhook без uuid/order_id', payload=payload)
            return None

        payment = None
        if uuid:
            payment = await pay2328_crud.get_pay2328_payment_by_uuid(db, uuid)
        if payment is None and order_id:
            payment = await pay2328_crud.get_pay2328_payment_by_order_id(db, order_id)

        if not payment:
            logger.error('2328.io платеж не найден', uuid=uuid, order_id=order_id)
            return None

        status_normalized = str(status or '').lower()

        if payment.transaction_id and status_normalized not in PAY2328_REFUND_STATUSES:
            logger.info('2328.io: платёж уже зачислен, вебхук пропущен', uuid=payment.uuid, status=status)
            return payment
        if (payment.status or '').lower() == 'refund_paid':
            return payment

        payer_amount = payload.get('payment_amount') or payload.get('payer_amount')
        payer_currency = payload.get('payer_currency')
        exchange_rate_raw = payload.get('exchange_rate')
        payment_url = payload.get('url')

        exchange_rate: float | None = None
        if exchange_rate_raw is not None:
            try:
                exchange_rate = float(exchange_rate_raw)
            except (TypeError, ValueError):
                exchange_rate = None

        if exchange_rate is None and payer_amount:
            try:
                exchange_rate = float(payer_amount) / payment.amount_float if payment.amount_float else None
            except (TypeError, ValueError, ZeroDivisionError):
                exchange_rate = None

        paid_at = datetime.now(UTC) if status_normalized in PAY2328_PAID_STATUSES else None

        updated_payment = await pay2328_crud.update_pay2328_payment(
            db,
            payment.uuid,
            status=status,
            payer_amount=str(payer_amount) if payer_amount is not None else None,
            payer_currency=str(payer_currency) if payer_currency is not None else None,
            exchange_rate=exchange_rate,
            paid_at=paid_at,
            payment_url=payment_url,
            metadata={metadata_key: payload},
        )

        if updated_payment is None:
            return None

        metadata = dict(getattr(updated_payment, 'metadata_json', {}) or {})
        invoice_message = metadata.get('invoice_message') or {}
        invoice_message_removed = False

        is_final = status_normalized in PAY2328_CLOSED_STATUSES

        if getattr(self, 'bot', None) and invoice_message and is_final:
            chat_id = invoice_message.get('chat_id')
            message_id = invoice_message.get('message_id')
            if chat_id and message_id:
                try:
                    await self.bot.delete_message(chat_id, message_id)
                except Exception as delete_error:  # pragma: no cover - depends on rights
                    logger.warning('Не удалось удалить счёт 2328.io', message_id=message_id, delete_error=delete_error)
                else:
                    metadata.pop('invoice_message', None)
                    invoice_message_removed = True

        if invoice_message_removed:
            try:
                from app.database.crud import pay2328 as pay2328_crud

                await pay2328_crud.update_pay2328_payment(
                    db,
                    updated_payment.uuid,
                    metadata=metadata,
                )
                updated_payment.metadata_json = metadata
            except Exception as error:  # pragma: no cover - diagnostics
                logger.warning('Не удалось обновить метаданные 2328.io после удаления счёта', error=error)

        pay2328_lock_crud = import_module('app.database.crud.pay2328')
        locked = await pay2328_lock_crud.get_pay2328_payment_by_id_for_update(db, updated_payment.id)
        if not locked:
            logger.error('2328.io: не удалось заблокировать платёж', payment_id=updated_payment.id)
            return None
        updated_payment = locked

        if updated_payment.transaction_id:
            logger.info(
                '2328.io платеж уже связан с транзакцией',
                uuid=updated_payment.uuid,
                transaction_id=updated_payment.transaction_id,
            )
            return updated_payment

        if status_normalized in PAY2328_MANUAL_REVIEW_STATUSES:
            logger.error(
                '2328.io: платёж требует ручной проверки, баланс не зачислен',
                uuid=updated_payment.uuid,
                status=status_normalized,
                user_id=updated_payment.user_id,
            )

        if status_normalized not in PAY2328_PAID_STATUSES:
            logger.info('2328.io платёж в этом статусе зачисления не требует', uuid=updated_payment.uuid, status=status)
            return updated_payment

        amount_kopeks = updated_payment.amount_kopeks
        if amount_kopeks <= 0:
            logger.error(
                '2328.io платеж имеет некорректную сумму', uuid=updated_payment.uuid, amount=updated_payment.amount
            )
            return None

        # --- Guest purchase flow (landing page) ---
        # Re-read metadata from the locked row to avoid stale data
        locked_metadata = dict(getattr(updated_payment, 'metadata_json', {}) or {})
        from app.services.payment.common import try_fulfill_guest_purchase

        guest_result = await try_fulfill_guest_purchase(
            db,
            metadata=locked_metadata,
            payment_amount_kopeks=amount_kopeks,
            provider_payment_id=updated_payment.uuid,
            provider_name='pay2328',
        )
        if guest_result is not None:
            return updated_payment

        transaction = await payment_module.create_transaction(
            db,
            user_id=updated_payment.user_id,
            type=TransactionType.DEPOSIT,
            amount_kopeks=amount_kopeks,
            description=(
                'Пополнение через 2328.io'
                if not updated_payment.payer_currency
                else (f'Пополнение через 2328.io ({updated_payment.payer_amount} {updated_payment.payer_currency})')
            ),
            payment_method=PaymentMethod.PAY2328,
            external_id=updated_payment.uuid,
            is_completed=True,
            created_at=getattr(updated_payment, 'created_at', None),
            commit=False,
        )

        linked_payment = await pay2328_crud.link_pay2328_payment_to_transaction(
            db,
            updated_payment.uuid,
            transaction.id,
        )
        if linked_payment:
            updated_payment = linked_payment

        get_user_by_id = payment_module.get_user_by_id
        user = await get_user_by_id(db, updated_payment.user_id)
        if not user:
            logger.error('Пользователь не найден для 2328.io платежа', user_id=updated_payment.user_id)
            return None

        # Lock user row to prevent concurrent balance race conditions
        from app.database.crud.user import lock_user_for_update

        user = await lock_user_for_update(db, user)

        old_balance = user.balance_kopeks
        was_first_topup = not user.has_made_first_topup

        user.balance_kopeks += amount_kopeks
        user.updated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(user)

        # Emit deferred side-effects after atomic commit
        from app.database.crud.transaction import emit_transaction_side_effects

        await emit_transaction_side_effects(
            db,
            transaction,
            amount_kopeks=amount_kopeks,
            user_id=updated_payment.user_id,
            type=TransactionType.DEPOSIT,
            payment_method=PaymentMethod.PAY2328,
            external_id=updated_payment.uuid,
        )

        try:
            from app.services.referral_service import process_referral_topup

            await process_referral_topup(
                db,
                user.id,
                amount_kopeks,
                getattr(self, 'bot', None),
            )
        except Exception as error:  # pragma: no cover - defensive
            logger.error('Ошибка реферального начисления 2328.io', error=error)

        if was_first_topup and not user.has_made_first_topup and not user.referred_by_id:
            user.has_made_first_topup = True
            await db.commit()
            await db.refresh(user)

        # Перезагружаем пользователя с зависимостями после коммита,
        # чтобы избежать lazy load в async-контексте (MissingGreenlet)
        user = await get_user_by_id(db, user.id) or user

        if getattr(self, 'bot', None):
            topup_status = '🆕 Первое пополнение' if was_first_topup else '🔄 Пополнение'
            referrer_info = format_referrer_info(user)
            subscription = getattr(user, 'subscription', None)
            promo_group = user.get_primary_promo_group()

            try:
                from app.services.admin_notification_service import AdminNotificationService

                notification_service = AdminNotificationService(self.bot)
                await notification_service.send_balance_topup_notification(
                    user,
                    transaction,
                    old_balance,
                    topup_status=topup_status,
                    referrer_info=referrer_info,
                    subscription=subscription,
                    promo_group=promo_group,
                    db=db,
                )
            except Exception as error:  # pragma: no cover
                logger.error('Ошибка отправки админ-уведомления 2328.io', error=error)

            # Отправляем уведомление только Telegram-пользователям
            if user.telegram_id and settings.is_notifications_enabled():
                try:
                    keyboard = await self.build_topup_success_keyboard(user)

                    await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=topup_success_text(user, amount_kopeks),
                        parse_mode='HTML',
                        reply_markup=keyboard,
                    )
                except Exception as error:  # pragma: no cover
                    logger.error('Ошибка отправки уведомления пользователю 2328.io', error=error)
            else:
                logger.info('Пропуск Telegram-уведомления 2328.io для email-пользователя', user_id=user.id)

        # Автопокупка из сохранённой корзины и уведомление о корзине
        try:
            from app.services.payment.common import send_cart_notification_after_topup

            await send_cart_notification_after_topup(
                user, updated_payment.amount_kopeks, db, getattr(self, 'bot', None)
            )
        except Exception as error:
            logger.error(
                'Ошибка при работе с автоактивацией для пользователя', user_id=user.id, error=error, exc_info=True
            )

        return updated_payment

    async def process_pay2328_webhook(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
    ) -> bool:
        result = await self._process_pay2328_payload(
            db,
            payload,
            metadata_key='last_webhook',
        )

        return result is not None

    async def sync_pay2328_payment_status(
        self,
        db: AsyncSession,
        *,
        local_payment_id: int,
    ) -> Pay2328Payment | None:
        if not getattr(self, 'pay2328_service', None):
            logger.error('2328.io сервис не инициализирован')
            return None

        pay2328_crud = import_module('app.database.crud.pay2328')

        payment = await pay2328_crud.get_pay2328_payment_by_id(db, local_payment_id)
        if not payment:
            logger.error('2328.io платеж с id= не найден', local_payment_id=local_payment_id)
            return None

        payload: dict[str, Any] | None = None
        try:
            response = await self.pay2328_service.get_payment_info(  # type: ignore[union-attr]
                uuid=payment.uuid,
                order_id=payment.order_id,
            )
        except Exception as error:  # pragma: no cover - defensive
            logger.exception('Ошибка получения статуса 2328.io платежа', uuid=payment.uuid, error=error)
        else:
            if response:
                result = response.get('result') if isinstance(response, dict) else None
                if isinstance(result, dict):
                    payload = dict(result)
                else:
                    logger.error(
                        'Некорректный ответ 2328.io API при проверке платежа', uuid=payment.uuid, response=response
                    )

        if payload is None:
            logger.warning('2328.io API не вернул информацию по платежу', uuid=payment.uuid)
            return payment

        payload.setdefault('uuid', payment.uuid)
        payload.setdefault('order_id', payment.order_id)

        updated_payment = await self._process_pay2328_payload(
            db,
            payload,
            metadata_key='last_status_check',
        )

        return updated_payment or payment
