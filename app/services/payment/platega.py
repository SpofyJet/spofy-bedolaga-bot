"""Mixin для интеграции платежей Platega."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import PaymentMethod, TransactionType
from app.services.payment.common import build_topup_success_message
from app.services.payment.payer_identity import PayerIdentity, payer_from_guest, resolve_user_payer
from app.services.payment_decline_notice import (
    DECLINE_NOTICE_KEY,
    NOTICE_SENT,
    decide_platega_decline_notice,
    send_platega_decline_notice,
)
from app.services.payment_problem_alert import alert_invoice_failed, alert_payment_not_applied, note_invoice_created
from app.services.payment_reversal_alert import alert_paid_payment_reversed
from app.services.platega_service import PlategaService
from app.utils.payment_logger import payment_logger as logger
from app.utils.user_utils import format_referrer_info


class PlategaPaymentMixin:
    """Логика создания и обработки платежей Platega."""

    _SUCCESS_STATUSES = {'CONFIRMED'}
    _FAILED_STATUSES = {'FAILED', 'CANCELED', 'EXPIRED'}
    _PENDING_STATUSES = {'PENDING', 'INPROGRESS'}

    # Повторное нажатие «Карта / СБП» с той же суммой отдаёт недавнюю ещё не оплаченную ссылку
    # вместо нового платежа у провайдера (раньше — новый платёж на каждое нажатие, иногда люди
    # оплачивали обе ссылки). Окно короче, чем напоминание о брошенной оплате (10-я минута):
    # кто вернулся по напоминанию «попробуйте ещё раз», получает новую ссылку, как и раньше.
    PLATEGA_REUSE_WINDOW = timedelta(minutes=10)
    # Ссылка должна прожить ещё хотя бы столько, чтобы успеть оплатить (Platega даёт 30 минут).
    PLATEGA_REUSE_MIN_TTL = timedelta(minutes=10)

    async def find_reusable_platega_payment(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        amount_kopeks: int,
        payment_method_code: int,
    ) -> dict[str, Any] | None:
        """Недавний платёж этого человека из бота на ту же сумму тем же способом — если он ещё жив.

        Живость проверяется у провайдера (тот же запрос, что у кнопки «Проверить статус»): только
        статус PENDING/INPROGRESS. Нет ответа, оплачен, отменён, истекает — None, и вызывающий
        создаёт новый платёж, как раньше. Зачисление по найденному платежу идёт прежним путём:
        вебхук и автопроверка находят его по transaction_id/correlation_id.
        """
        from app.database.models import PlategaPayment

        now = datetime.now(UTC)
        candidate = await db.scalar(
            select(PlategaPayment)
            .where(
                PlategaPayment.user_id == user_id,
                PlategaPayment.amount_kopeks == amount_kopeks,
                PlategaPayment.payment_method_code == payment_method_code,
                PlategaPayment.status.in_(self._PENDING_STATUSES),
                PlategaPayment.is_paid.is_not(True),
                PlategaPayment.transaction_id.is_(None),
                PlategaPayment.redirect_url.is_not(None),
                PlategaPayment.platega_transaction_id.is_not(None),
                PlategaPayment.created_at >= now - self.PLATEGA_REUSE_WINDOW,
                PlategaPayment.expires_at >= now + self.PLATEGA_REUSE_MIN_TTL,
                # Только платежи пополнения из бота: у кабинета свои адреса возврата.
                PlategaPayment.return_url.is_not_distinct_from(settings.get_platega_return_url()),
                PlategaPayment.failed_url.is_not_distinct_from(settings.get_platega_failed_url()),
            )
            .order_by(PlategaPayment.created_at.desc())
            .limit(1)
        )
        if candidate is None or (candidate.metadata_json or {}).get('purchase_token'):
            return None

        try:
            checked = await self.get_platega_payment_status(db, candidate.id)
        except Exception as error:  # сеть, провайдер — новый платёж, как раньше
            logger.warning('Platega: не удалось проверить прежний платёж', payment_id=candidate.id, error=error)
            return None
        remote = (checked or {}).get('remote')
        remote_status = str((remote or {}).get('status') or '').upper()
        payment = (checked or {}).get('payment')
        if not remote or remote_status not in self._PENDING_STATUSES or payment is None or payment.is_paid:
            return None

        logger.info(
            'Platega: повторное нажатие — отдаём прежнюю ссылку',
            payment_id=payment.id,
            user_id=user_id,
            payment_method_code=payment_method_code,
        )
        return {
            'local_payment_id': payment.id,
            'transaction_id': payment.platega_transaction_id,
            'redirect_url': payment.redirect_url,
            'status': payment.status,
            'expires_at': payment.expires_at,
            'correlation_id': payment.correlation_id,
            'payload': payment.payload,
            'reused': True,
        }

    async def create_platega_payment(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        amount_kopeks: int,
        description: str,
        language: str,
        payment_method_code: int,
        return_url: str | None = None,
        failed_url: str | None = None,
        payer: PayerIdentity | None = None,
    ) -> dict[str, Any] | None:
        """Разовый платёж Platega. ``payer`` — плательщик-гость лендинга; у пользователя
        он читается по ``user_id`` (metadata.userId/userName обязательны, см. payer_identity)."""
        service: PlategaService | None = getattr(self, 'platega_service', None)
        if not service or not service.is_configured:
            logger.error('Platega сервис не инициализирован')
            return None

        if amount_kopeks < settings.PLATEGA_MIN_AMOUNT_KOPEKS:
            logger.warning(
                'Сумма Platega меньше минимальной: <',
                amount_kopeks=amount_kopeks,
                PLATEGA_MIN_AMOUNT_KOPEKS=settings.PLATEGA_MIN_AMOUNT_KOPEKS,
            )
            return None

        if amount_kopeks > settings.PLATEGA_MAX_AMOUNT_KOPEKS:
            logger.warning(
                'Сумма Platega больше максимальной: >',
                amount_kopeks=amount_kopeks,
                PLATEGA_MAX_AMOUNT_KOPEKS=settings.PLATEGA_MAX_AMOUNT_KOPEKS,
            )
            return None

        correlation_id = uuid.uuid4().hex
        payload_token = f'platega:{correlation_id}'

        amount_value = amount_kopeks / 100

        effective_return_url = return_url or settings.get_platega_return_url()
        effective_failed_url = failed_url or settings.get_platega_failed_url()

        if payer is None:
            payer = (
                await resolve_user_payer(db, user_id)
                if user_id is not None
                # Ни пользователя, ни гостя вызывающий не дал — плательщик по id платежа.
                else payer_from_guest(correlation_id, contact_type=None, contact_value=None)
            )

        try:
            response = await service.create_payment(
                payer=payer,
                payment_method=payment_method_code,
                amount=amount_value,
                currency=settings.PLATEGA_CURRENCY,
                description=description,
                return_url=effective_return_url,
                failed_url=effective_failed_url,
                payload=payload_token,
            )
        except Exception as error:  # pragma: no cover - network errors
            logger.exception('Ошибка Platega при создании платежа', error=error)
            await alert_invoice_failed(
                getattr(self, 'bot', None),
                provider='Platega',
                reason=type(error).__name__,
                user_id=user_id,
                amount_kopeks=amount_kopeks,
            )
            return None

        if not response:
            logger.error('Platega вернул пустой ответ при создании платежа')
            await alert_invoice_failed(
                getattr(self, 'bot', None),
                provider='Platega',
                reason='пустой ответ',
                user_id=user_id,
                amount_kopeks=amount_kopeks,
            )
            return None

        note_invoice_created('Platega')

        transaction_id = response.get('transactionId') or response.get('id')
        redirect_url = PlategaService.parse_redirect_url(response)
        status = str(response.get('status') or 'PENDING').upper()
        expires_at = PlategaService.parse_expires_at(response.get('expiresIn'))

        metadata = {
            'raw_response': response,
            'language': language,
            'selected_method': payment_method_code,
        }

        payment_module = import_module('app.services.payment_service')

        payment = await payment_module.create_platega_payment(
            db,
            user_id=user_id,
            amount_kopeks=amount_kopeks,
            currency=settings.PLATEGA_CURRENCY,
            description=description,
            status=status,
            payment_method_code=payment_method_code,
            correlation_id=correlation_id,
            platega_transaction_id=transaction_id,
            redirect_url=redirect_url,
            return_url=effective_return_url,
            failed_url=effective_failed_url,
            payload=payload_token,
            metadata=metadata,
            expires_at=expires_at,
        )

        logger.info(
            f'Создан Platega платёж для {"пользователя " + str(user_id) if user_id is not None else "гостя"} '
            f'(метод {payment_method_code}, сумма {amount_value:.2f} {settings.PLATEGA_CURRENCY})',
            transaction_id=transaction_id or payment.id,
            user_id=user_id,
            payment_method_code=payment_method_code,
            amount_value=amount_value,
        )

        return {
            'local_payment_id': payment.id,
            'transaction_id': transaction_id,
            'redirect_url': redirect_url,
            'status': status,
            'expires_at': expires_at,
            'correlation_id': correlation_id,
            'payload': payload_token,
        }

    async def process_platega_webhook(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
    ) -> bool:
        payment_module = import_module('app.services.payment_service')

        transaction_id = str(payload.get('id') or '').strip()
        payload_token = payload.get('payload')

        payment = None
        if transaction_id:
            payment = await payment_module.get_platega_payment_by_transaction_id(db, transaction_id)
        if not payment and payload_token:
            payment = await payment_module.get_platega_payment_by_correlation_id(
                db, str(payload_token).replace('platega:', '')
            )

        if not payment:
            logger.warning('Platega webhook: платеж не найден', transaction_id=transaction_id)
            return False

        # Lock payment row immediately to prevent concurrent webhook processing (TOCTOU race)
        platega_crud = import_module('app.database.crud.platega')
        locked = await platega_crud.get_platega_payment_by_id_for_update(db, payment.id)
        if not locked:
            logger.error('Platega: не удалось заблокировать платёж', payment_id=payment.id)
            return False
        payment = locked

        status_raw = str(payload.get('status') or '').upper()
        if not status_raw:
            logger.warning('Platega webhook без статуса для платежа', payment_id=payment.id)
            return False

        if status_raw in self._SUCCESS_STATUSES:
            if payment.is_paid:
                logger.info('Platega платеж уже помечен как оплачен', correlation_id=payment.correlation_id)
                # Update callback payload without releasing the lock prematurely
                payment.callback_payload = payload
                if transaction_id and not payment.platega_transaction_id:
                    payment.platega_transaction_id = transaction_id
                payment.updated_at = datetime.now(UTC)
                await db.commit()
                return True

            # Inline field updates — NO intermediate commit that would release FOR UPDATE lock
            payment.status = status_raw
            payment.callback_payload = payload
            if transaction_id and not payment.platega_transaction_id:
                payment.platega_transaction_id = transaction_id
            payment.updated_at = datetime.now(UTC)
            await db.flush()

            result = await self._finalize_platega_payment(db, payment, payload)
            if result is None:
                logger.error('Platega webhook: финализация не удалась', payment_id=payment.id)
                return False
            return True

        if payment.is_paid and status_raw not in self._PENDING_STATUSES:
            # Оплаченный платёж ушёл в CHARGEBACKED/REFUNDED/FAILED: is_paid не сбрасываем
            # (повторный CONFIRMED иначе финализировал бы платёж ещё раз), зовём админа.
            await payment_module.update_platega_payment(
                db,
                payment=payment,
                status=status_raw,
                callback_payload=payload,
                platega_transaction_id=transaction_id or None,
            )
            await alert_paid_payment_reversed(
                getattr(self, 'bot', None),
                provider='Platega',
                local_payment_id=payment.id,
                user_id=payment.user_id,
                amount_kopeks=payment.amount_kopeks,
                status=status_raw,
            )
            return True

        if status_raw in self._FAILED_STATUSES:
            # Отказ банка: решаем один раз, под блокировкой строки, и записываем решение вместе
            # со статусом — повтор вебхука второго сообщения не даст.
            bot = getattr(self, 'bot', None)
            try:
                notice, notice_user = await decide_platega_decline_notice(db, payment, status_raw, bot=bot)
            except Exception as error:  # сообщение человеку не должно мешать записи статуса
                logger.warning('Platega: не удалось решить, писать ли об отказе', payment_id=payment.id, error=error)
                notice, notice_user = None, None
            metadata = None
            if notice is not None:
                metadata = {**(getattr(payment, 'metadata_json', None) or {}), DECLINE_NOTICE_KEY: notice}
            await payment_module.update_platega_payment(
                db,
                payment=payment,
                status=status_raw,
                callback_payload=payload,
                platega_transaction_id=transaction_id or None,
                is_paid=False,
                metadata=metadata,
            )
            logger.info('Platega платеж перешёл в статус', correlation_id=payment.correlation_id, status_raw=status_raw)
            if notice == NOTICE_SENT and notice_user is not None:
                await send_platega_decline_notice(db, bot, notice_user, payment)
            return True

        await payment_module.update_platega_payment(
            db,
            payment=payment,
            status=status_raw,
            callback_payload=payload,
            platega_transaction_id=transaction_id or None,
        )
        return True

    async def get_platega_payment_status(
        self,
        db: AsyncSession,
        local_payment_id: int,
    ) -> dict[str, Any] | None:
        payment_module = import_module('app.services.payment_service')
        payment = await payment_module.get_platega_payment_by_id(db, local_payment_id)
        if not payment:
            return None

        service: PlategaService | None = getattr(self, 'platega_service', None)
        remote_status: str | None = None
        remote_payload: dict[str, Any] | None = None

        if service and payment.platega_transaction_id:
            # Запрос к провайдеру идёт секунды: соединение с базой на это время не держим.
            await db.commit()
            try:
                remote_payload = await service.get_transaction(payment.platega_transaction_id)
            except Exception as error:  # pragma: no cover - network errors
                logger.error(
                    'Ошибка Platega при получении транзакции',
                    platega_transaction_id=payment.platega_transaction_id,
                    error=error,
                )

        if remote_payload:
            remote_status = str(remote_payload.get('status') or '').upper()
            status_changed = remote_status and remote_status != payment.status

            if remote_status in self._SUCCESS_STATUSES and not payment.is_paid:
                # Lock payment row before finalization to prevent concurrent double-processing
                platega_crud = import_module('app.database.crud.platega')
                locked = await platega_crud.get_platega_payment_by_id_for_update(db, payment.id)
                if not locked:
                    logger.error('Platega status check: не удалось заблокировать платёж', payment_id=payment.id)
                elif locked.is_paid:
                    # Another concurrent handler already processed — skip
                    logger.info('Platega платеж уже оплачен после блокировки', correlation_id=locked.correlation_id)
                    payment = locked
                else:
                    payment = locked
                    payment.status = remote_status
                    payment.callback_payload = remote_payload
                    payment.metadata_json = {
                        **(getattr(payment, 'metadata_json', {}) or {}),
                        'remote_status': remote_payload,
                    }
                    payment.updated_at = datetime.now(UTC)
                    await db.flush()
                    result = await self._finalize_platega_payment(db, payment, remote_payload)
                    if result is not None:
                        payment = result
            elif status_changed:
                # Non-success status change — safe to persist without lock
                payment.status = remote_status
                payment.metadata_json = {
                    **(getattr(payment, 'metadata_json', {}) or {}),
                    'remote_status': remote_payload,
                }
                payment.updated_at = datetime.now(UTC)
                await db.commit()

        return {
            'payment': payment,
            'status': payment.status,
            'is_paid': payment.is_paid,
            'remote': remote_payload,
        }

    async def _finalize_platega_payment(
        self,
        db: AsyncSession,
        payment: Any,
        payload: dict[str, Any] | None,
    ) -> Any:
        payment_module = import_module('app.services.payment_service')

        paid_at = None
        if isinstance(payload, dict):
            paid_at_raw = payload.get('paidAt') or payload.get('confirmedAt')
            if paid_at_raw:
                try:
                    paid_at_parsed = datetime.fromisoformat(str(paid_at_raw))
                    paid_at = paid_at_parsed if paid_at_parsed.tzinfo else paid_at_parsed.replace(tzinfo=UTC)
                except ValueError:
                    paid_at = None

        # FOR UPDATE lock already acquired by caller — just check idempotency
        if payment.transaction_id:
            logger.info(
                'Platega платеж уже связан с транзакцией',
                correlation_id=payment.correlation_id,
                transaction_id=payment.transaction_id,
            )
            return payment

        # Read fresh metadata AFTER lock to avoid stale data
        metadata = dict(getattr(payment, 'metadata_json', {}) or {})

        # --- Guest purchase flow (landing page) ---
        from app.services.payment.common import try_fulfill_guest_purchase

        guest_result = await try_fulfill_guest_purchase(
            db,
            metadata=metadata,
            payment_amount_kopeks=payment.amount_kopeks,
            provider_payment_id=payment.correlation_id,
            provider_name='platega',
        )
        if guest_result is not None:
            return payment

        if payload is not None:
            metadata['webhook'] = payload

        # Inline field assignments instead of update_platega_payment() which commits
        # and would release the FOR UPDATE lock prematurely
        payment.status = 'CONFIRMED'
        payment.is_paid = True
        if paid_at is not None:
            payment.paid_at = paid_at
        payment.metadata_json = metadata
        if payload is not None:
            payment.callback_payload = payload
        payment.updated_at = datetime.now(UTC)

        balance_already_credited = bool(metadata.get('balance_credited'))

        invoice_message = metadata.get('invoice_message') or {}
        if getattr(self, 'bot', None):
            chat_id = invoice_message.get('chat_id')
            message_id = invoice_message.get('message_id')
            if chat_id and message_id:
                try:
                    await self.bot.delete_message(chat_id, message_id)
                except Exception as delete_error:  # pragma: no cover - depends on bot rights
                    logger.warning('Не удалось удалить Platega счёт', message_id=message_id, delete_error=delete_error)
                else:
                    metadata.pop('invoice_message', None)

        user = await payment_module.get_user_by_id(db, payment.user_id)
        if not user:
            logger.error('Пользователь не найден для Platega', user_id=payment.user_id)
            # Платёж уже помечен оплаченным и закоммитится вызывающим — повторов
            # не будет, оповещение уходит один раз.
            await alert_payment_not_applied(
                getattr(self, 'bot', None),
                provider='Platega',
                problem='Оплата получена, но пользователь не найден — баланс не пополнен',
                user_id=payment.user_id,
                amount_kopeks=payment.amount_kopeks,
                reference=str(payment.correlation_id),
            )
            return payment

        # Убеждаемся, что промогруппы загружены в асинхронном контексте,
        # чтобы избежать попыток ленивой загрузки без greenlet
        await db.refresh(user, attribute_names=['promo_group', 'user_promo_groups'])
        for user_promo_group in getattr(user, 'user_promo_groups', []):
            await db.refresh(user_promo_group, attribute_names=['promo_group'])

        promo_group = user.get_primary_promo_group()
        subscription = getattr(user, 'subscription', None)
        referrer_info = format_referrer_info(user)

        transaction_external_id = (
            str(payload.get('id'))
            if isinstance(payload, dict) and payload.get('id')
            else payment.platega_transaction_id
        )

        existing_transaction = None
        if transaction_external_id:
            existing_transaction = await payment_module.get_transaction_by_external_id(
                db,
                transaction_external_id,
                PaymentMethod.PLATEGA,
            )

        platega_name = settings.get_platega_display_name()
        method_display = settings.get_platega_method_display_name(payment.payment_method_code)
        description = (
            f'Пополнение через {platega_name} ({method_display})'
            if method_display
            else f'Пополнение через {platega_name}'
        )

        transaction = existing_transaction
        created_transaction = False

        if not transaction:
            transaction = await payment_module.create_transaction(
                db,
                user_id=payment.user_id,
                type=TransactionType.DEPOSIT,
                amount_kopeks=payment.amount_kopeks,
                description=description,
                payment_method=PaymentMethod.PLATEGA,
                external_id=transaction_external_id or payment.correlation_id,
                is_completed=True,
                created_at=getattr(payment, 'created_at', None),
                commit=False,
            )
            created_transaction = True

        await payment_module.link_platega_payment_to_transaction(db, payment=payment, transaction_id=transaction.id)

        should_credit_balance = created_transaction or not balance_already_credited

        if not should_credit_balance:
            logger.info('Platega платеж уже зачислил баланс ранее', correlation_id=payment.correlation_id)
            return payment

        # Lock user row to prevent concurrent balance race conditions
        from app.database.crud.user import lock_user_for_update

        user = await lock_user_for_update(db, user)

        old_balance = user.balance_kopeks
        was_first_topup = not user.has_made_first_topup

        user.balance_kopeks += payment.amount_kopeks
        user.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(user)

        # Emit deferred side-effects after atomic commit
        from app.database.crud.transaction import emit_transaction_side_effects

        await emit_transaction_side_effects(
            db,
            transaction,
            amount_kopeks=payment.amount_kopeks,
            user_id=payment.user_id,
            type=TransactionType.DEPOSIT,
            payment_method=PaymentMethod.PLATEGA,
            external_id=transaction_external_id or payment.correlation_id,
        )

        topup_status = '🆕 Первое пополнение' if was_first_topup else '🔄 Пополнение'

        try:
            from app.services.referral_service import process_referral_topup

            await process_referral_topup(
                db,
                user.id,
                payment.amount_kopeks,
                getattr(self, 'bot', None),
            )
        except Exception as error:
            logger.error('Ошибка обработки реферального пополнения Platega', error=error)

        if was_first_topup and not user.has_made_first_topup and not user.referred_by_id:
            user.has_made_first_topup = True
            await db.commit()
            await db.refresh(user)

        if getattr(self, 'bot', None):
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
            except Exception as error:
                logger.error('Ошибка отправки админ уведомления Platega', error=error)

        if getattr(self, 'bot', None) and user.telegram_id and settings.is_notifications_enabled():
            try:
                text, keyboard = await build_topup_success_message(self, user, payment.amount_kopeks)
                await self.bot.send_message(
                    user.telegram_id,
                    text,
                    parse_mode='HTML',
                    reply_markup=keyboard,
                )
            except Exception as error:
                logger.error('Ошибка отправки уведомления пользователю Platega', error=error)

        try:
            from app.services.payment.common import send_cart_notification_after_topup

            await send_cart_notification_after_topup(user, payment.amount_kopeks, db, getattr(self, 'bot', None))
        except Exception as error:
            logger.error(
                'Ошибка при работе с сохраненной корзиной для пользователя',
                user_id=payment.user_id,
                error=error,
                exc_info=True,
            )

        metadata['balance_change'] = {
            'old_balance': old_balance,
            'new_balance': user.balance_kopeks,
            'credited_at': datetime.now(UTC).isoformat(),
        }
        metadata['balance_credited'] = True

        await payment_module.update_platega_payment(
            db,
            payment=payment,
            metadata=metadata,
        )

        logger.info(
            '✅ Обработан Platega платеж для пользователя',
            correlation_id=payment.correlation_id,
            user_id=payment.user_id,
        )

        return payment
