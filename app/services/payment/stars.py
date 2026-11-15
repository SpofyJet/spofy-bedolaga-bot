"""Логика Telegram Stars вынесена в отдельный mixin.

Методы здесь отвечают только за работу с звёздами, что позволяет держать
основной сервис компактным и облегчает тестирование конкретных сценариев.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.transaction import (
    create_transaction,
    emit_transaction_side_effects,
    get_transaction_by_external_id,
)
from app.database.crud.user import get_user_by_id
from app.database.models import PaymentMethod, TransactionType
from app.external.telegram_stars import TelegramStarsService
from app.utils.payment_logger import payment_logger as logger
from app.utils.user_utils import format_referrer_info


class TelegramStarsMixin:
    """Mixin с операциями создания и обработки платежей через Telegram Stars."""

    async def create_stars_invoice(
        self,
        amount_kopeks: int,
        description: str,
        payload: str | None = None,
        *,
        stars_amount: int | None = None,
    ) -> str:
        """Создаёт invoice в Telegram Stars, автоматически рассчитывая количество звёзд."""
        if not self.bot or not getattr(self, 'stars_service', None):
            raise ValueError('Bot instance required for Stars payments')

        try:
            amount_rubles = Decimal(amount_kopeks) / Decimal(100)

            # Если количество звёзд не задано, вычисляем его из курса.
            if stars_amount is None:
                stars_amount = settings.rubles_to_stars(float(amount_rubles))

            if stars_amount <= 0:
                raise ValueError('Stars amount must be positive')

            invoice_link = await self.bot.create_invoice_link(
                title='Пополнение баланса VPN',
                description=f'{description} (≈{stars_amount} ⭐)',
                payload=payload or f'balance_topup_{amount_kopeks}',
                provider_token='',
                currency='XTR',
                prices=[LabeledPrice(label='Пополнение', amount=stars_amount)],
            )

            logger.info(
                'Создан Stars invoice на звезд (~)',
                stars_amount=stars_amount,
                format_price=settings.format_price(amount_kopeks),
            )
            return invoice_link

        except Exception as error:
            logger.error('Ошибка создания Stars invoice', error=error)
            raise

    async def process_stars_payment(
        self,
        db: AsyncSession,
        user_id: int,
        stars_amount: int,
        payload: str,
        telegram_payment_charge_id: str,
    ) -> bool:
        """Финализирует платеж, пришедший из Telegram Stars, и обновляет баланс пользователя.

        Credit derivation order:
          1. If payload encodes the originally-requested ``amount_kopeks``
             (every balance-topup flow does this), credit that exact
             amount. This is what the user actually asked for; the
             stars-to-rubles back-conversion can drift by sub-ruble
             fractions (banker's rounding at quote time, non-1.0
             operator rates).
          2. Otherwise fall back to ``stars × current_rate`` — best-effort
             for old payloads or paths we haven't catalogued.

        Telegram passes the payload back byte-for-byte from the
        ``create_invoice_link`` call, so payload trust is fine; the
        sanity bound below catches obviously-bogus encodings.
        """
        try:
            # Идемпотентность: Telegram может повторно прислать successful_payment
            # (например, если бот не успел подтвердить обработку до таймаута). Ключ
            # уникальности — telegram_payment_charge_id. Если транзакция с таким
            # external_id уже есть — платёж обработан, выходим как успех.
            existing_transaction = await get_transaction_by_external_id(
                db, telegram_payment_charge_id, PaymentMethod.TELEGRAM_STARS
            )
            if existing_transaction:
                logger.info(
                    'Stars платёж уже обработан — пропускаю повторную обработку',
                    telegram_payment_charge_id=telegram_payment_charge_id,
                )
                return True

            rubles_amount = TelegramStarsService.calculate_rubles_from_stars(stars_amount)
            reconstructed_kopeks = int((rubles_amount * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))

            payload_kopeks = self._parse_balance_topup_kopeks(payload)
            if payload_kopeks is not None and self._is_payload_amount_plausible(
                payload_kopeks=payload_kopeks,
                reconstructed_kopeks=reconstructed_kopeks,
            ):
                amount_kopeks = payload_kopeks
            else:
                if payload_kopeks is not None:
                    logger.warning(
                        'Stars payload amount diverged from stars×rate; using reconstructed amount',
                        payload_kopeks=payload_kopeks,
                        reconstructed_kopeks=reconstructed_kopeks,
                        stars_amount=stars_amount,
                    )
                amount_kopeks = reconstructed_kopeks

            transaction_description = f'Пополнение через Telegram Stars ({stars_amount} ⭐)'
            transaction_type = TransactionType.DEPOSIT

            # commit=False: транзакция флашится, но не коммитится здесь. Реальный
            # коммит происходит атомарно вместе с зачислением баланса —
            # так нет окна, где транзакция записана, а баланс нет.
            transaction = await create_transaction(
                db=db,
                user_id=user_id,
                type=transaction_type,
                amount_kopeks=amount_kopeks,
                description=transaction_description,
                payment_method=PaymentMethod.TELEGRAM_STARS,
                external_id=telegram_payment_charge_id,
                is_completed=True,
                commit=False,
            )

            user = await get_user_by_id(db, user_id)
            if not user:
                logger.error('Пользователь с ID не найден при обработке Stars платежа', user_id=user_id)
                await db.rollback()
                return False

            return await self._finalize_stars_balance_topup(
                db=db,
                user=user,
                transaction=transaction,
                amount_kopeks=amount_kopeks,
                stars_amount=stars_amount,
                telegram_payment_charge_id=telegram_payment_charge_id,
            )

        except Exception as error:
            logger.error('Ошибка обработки Stars платежа', error=error, exc_info=True)
            # Откатываем незакоммиченную транзакцию (commit=False), чтобы она не
            # «дозалипла» и не закоммитилась случайно мидлварью при выходе.
            try:
                await db.rollback()
            except Exception:
                logger.warning('Ignored error in process_stars_payment', exc_info=True)
            return False

    @staticmethod
    def _parse_balance_topup_kopeks(payload: str) -> int | None:
        """Extract the original ``amount_kopeks`` from a balance-topup payload.

        Known producers (and the slot where amount_kopeks lives):
          * ``balance_topup_{kopeks}``                           — bot, services/payment/stars.py
          * ``balance_{user_id}_{kopeks}``                       — miniapp.py
          * ``balance_{user_id}_{kopeks}_{suffix}``              — miniapp variant
          * ``balance_topup_{user_id}_{kopeks}_{ts}``            — cabinet/routes/balance.py

        Returns ``None`` for any payload that doesn't match a known
        balance-topup shape. Callers should handle that
        case by falling back to the stars-to-rubles back-conversion.
        """
        if not payload or not payload.startswith('balance'):
            return None

        parts = payload.split('_')
        # parts[0] == 'balance' guaranteed by the prefix check above.

        candidate: str | None = None
        if len(parts) >= 2 and parts[1] == 'topup':
            # `balance_topup_{kopeks}`               → kopeks at index 2
            # `balance_topup_{uid}_{kopeks}_{ts}`    → kopeks at index 3
            if len(parts) == 3:
                candidate = parts[2]
            elif len(parts) >= 4:
                candidate = parts[3]
        elif len(parts) >= 3:
            # `balance_{uid}_{kopeks}[_suffix]`      → kopeks at index 2
            candidate = parts[2]

        if candidate is None:
            return None
        try:
            kopeks = int(candidate)
        except ValueError:
            return None
        return kopeks if kopeks > 0 else None

    @staticmethod
    def _is_payload_amount_plausible(
        *,
        payload_kopeks: int,
        reconstructed_kopeks: int,
    ) -> bool:
        """Sanity bound: payload amount must be in the same ballpark as stars×rate.

        Rejects pathological payloads that would massively over-credit
        the user. The bound is intentionally generous (20% or 100
        kopeks, whichever is larger) so legitimate rate changes between
        invoice creation and payment, or precision quirks at fractional
        rubles, don't trip it.

        Telegram passes the payload back verbatim from ``create_invoice_link``
        so external tampering is not the threat model — this is a bug
        catcher for misconfigured callers, not a security boundary.
        """
        if payload_kopeks <= 0 or reconstructed_kopeks <= 0:
            return False
        tolerance = max(int(reconstructed_kopeks * 0.20), 100)
        return abs(payload_kopeks - reconstructed_kopeks) <= tolerance

    async def _finalize_stars_balance_topup(
        self,
        db: AsyncSession,
        user,
        transaction,
        amount_kopeks: int,
        stars_amount: int,
        telegram_payment_charge_id: str,
    ) -> bool:
        """Начисляет баланс пользователю после оплаты Stars и запускает автопокупку."""

        # Lock user row to prevent concurrent balance race conditions
        from app.database.crud.user import lock_user_for_update

        user = await lock_user_for_update(db, user)

        # Запоминаем старые значения, чтобы корректно построить уведомления.
        old_balance = user.balance_kopeks
        was_first_topup = not user.has_made_first_topup

        # Обновляем баланс в БД.
        user.balance_kopeks += amount_kopeks
        user.updated_at = datetime.now(UTC)

        promo_group = user.get_primary_promo_group()
        subscription = getattr(user, 'subscription', None)
        referrer_info = format_referrer_info(user)
        topup_status = '🆕 Первое пополнение' if was_first_topup else '🔄 Пополнение'

        await db.commit()

        # Баланс и транзакция (она создавалась с commit=False) закоммичены атомарно.
        # Шлём отложенные побочки: событие payment.completed и автовыдачу промогруппы.
        await emit_transaction_side_effects(
            db,
            transaction,
            amount_kopeks=amount_kopeks,
            user_id=user.id,
            type=TransactionType.DEPOSIT,
            payment_method=PaymentMethod.TELEGRAM_STARS,
            external_id=telegram_payment_charge_id,
            is_completed=True,
            description=transaction.description,
        )

        description_for_referral = f'Пополнение Stars: {settings.format_price(amount_kopeks)} ({stars_amount} ⭐)'
        logger.info('🔍 Проверка реферальной логики для описания', description_for_referral=description_for_referral)

        lower_description = description_for_referral.lower()
        contains_allowed_keywords = any(word in lower_description for word in ['пополнение', 'stars', 'topup'])
        contains_forbidden_keywords = any(word in lower_description for word in ['комиссия', 'бонус'])
        allow_referral = contains_allowed_keywords and not contains_forbidden_keywords

        if allow_referral:
            logger.info('🔞 Вызов process_referral_topup для пользователя', user_id=user.id)
            try:
                from app.services.referral_service import process_referral_topup

                await process_referral_topup(
                    db,
                    user.id,
                    amount_kopeks,
                    getattr(self, 'bot', None),
                )
            except Exception as error:  # pragma: no cover - диагностический лог
                logger.error('Ошибка обработки реферального пополнения', error=error)
        else:
            logger.info(
                '❌ Описание не подходит для реферальной логики', description_for_referral=description_for_referral
            )

        if was_first_topup and not user.has_made_first_topup and not user.referred_by_id:
            user.has_made_first_topup = True
            await db.commit()

        await db.refresh(user)

        logger.info(
            '💰 Баланс пользователя изменен: → (Δ +)',
            telegram_id=user.telegram_id,
            old_balance=old_balance,
            balance_kopeks=user.balance_kopeks,
            amount_kopeks=amount_kopeks,
        )

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
            except Exception as error:  # pragma: no cover - диагностический лог
                logger.error('Ошибка отправки уведомления о пополнении Stars', error=error, exc_info=True)

        # Проверяем наличие сохраненной корзины для возврата к оформлению подписки
        try:
            from app.services.payment.common import send_cart_notification_after_topup

            await send_cart_notification_after_topup(user, amount_kopeks, db, getattr(self, 'bot', None))
        except Exception as error:  # pragma: no cover - диагностический лог
            logger.error(
                'Ошибка при работе с сохраненной корзиной для пользователя', user_id=user.id, error=error, exc_info=True
            )

        logger.info(
            '✅ Обработан Stars платеж',
            user_id=user.id,
            stars_amount=stars_amount,
            format_price=settings.format_price(amount_kopeks),
        )
        return True


def stars_to_kopeks(stars_amount: int) -> int:
    """Рубли за звёзды по текущему курсу — так же, как считается пополнение Stars."""
    rubles = TelegramStarsService.calculate_rubles_from_stars(stars_amount)
    return int((rubles * Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))


async def credit_unapplied_stars_payment(
    db: AsyncSession,
    *,
    user,
    stars_amount: int,
    telegram_payment_charge_id: str | None,
    problem: str,
    bot=None,
    details: dict | None = None,
) -> int | None:
    """Оплата Stars прошла, а применить её по назначению нельзя — зачисляем на баланс.

    Звёзды Telegram сам не возвращает и successful_payment не повторяет «по ошибке»,
    поэтому без этого деньги пропадают. Зачисление — DEPOSIT с external_id =
    telegram_payment_charge_id: повторная доставка того же платежа второй раз не
    зачислит (проверка + уникальный индекс external_id/payment_method).

    Возвращает зачисленную сумму в копейках (в том числе если её зачислили раньше)
    или None, если зачислить не вышло — тогда админы получают оповещение.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.database.crud.user import add_user_balance
    from app.services.payment_problem_alert import alert_payment_not_applied

    # Вызывают обычно после db.rollback(): объект пользователя истёк, и ленивая
    # загрузка атрибута в async-сессии упала бы. Берём id из identity и перечитываем.
    state = sa_inspect(user, raiseerr=False)
    if state is not None and state.identity:
        user = await get_user_by_id(db, state.identity[0]) or user

    charge_id = telegram_payment_charge_id or None
    if charge_id:
        existing = await get_transaction_by_external_id(db, charge_id, PaymentMethod.TELEGRAM_STARS)
        if existing:
            logger.info(
                'Stars платёж уже зачислен на баланс — повтор пропущен',
                telegram_payment_charge_id=charge_id,
                user_id=user.id,
            )
            return abs(existing.amount_kopeks)

    amount_kopeks = stars_to_kopeks(stars_amount)
    alert_details = {'Telegram ID': getattr(user, 'telegram_id', None), 'Stars': stars_amount, **(details or {})}

    credited = amount_kopeks > 0 and await add_user_balance(
        db,
        user,
        amount_kopeks,
        # Описание видно человеку в истории баланса — без внутренних причин (они в алерте).
        f'Оплата Telegram Stars зачислена на баланс ({stars_amount} ⭐)',
        transaction_type=TransactionType.DEPOSIT,
        payment_method=PaymentMethod.TELEGRAM_STARS,
        external_id=charge_id,
    )
    if not credited:
        if charge_id:
            # Параллельная доставка того же платежа успела зачислить первой.
            existing = await get_transaction_by_external_id(db, charge_id, PaymentMethod.TELEGRAM_STARS)
            if existing:
                return abs(existing.amount_kopeks)
        await alert_payment_not_applied(
            bot,
            provider='telegram_stars',
            problem=f'{problem}. Зачислить на баланс не удалось — нужна ручная проверка',
            user_id=user.id,
            amount_kopeks=amount_kopeks,
            reference=charge_id,
            details=alert_details,
        )
        return None

    await alert_payment_not_applied(
        bot,
        provider='telegram_stars',
        problem=f'{problem}. Оплата зачислена на баланс пользователя',
        user_id=user.id,
        amount_kopeks=amount_kopeks,
        reference=charge_id,
        details=alert_details,
    )
    return amount_kopeks
