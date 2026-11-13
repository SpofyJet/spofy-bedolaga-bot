"""Банк отклонил оплату: одно сообщение с кнопками «ещё раз» и «другой способ».

Platega на отклонённую или отменённую оплату присылает ``CANCELED`` — и тот же ``CANCELED``, когда
счёт просто истёк неоткрытым (через 30 минут). Причины в ответе нет, различает их только время:
отказ приходит, пока счёт ещё жив (за 30 дней — 140 счетов, почти все через 3–4 минуты после
создания), истечение — после ``expires_at`` (325 счетов). Пишем только в первом случае.

Раньше человек узнавал об отказе из общего напоминания «Оплата не завершена» через 10+ минут
(его получала половина) или не узнавал вовсе.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import PlategaPayment, SubscriptionEvent, Transaction, TransactionType, User, UserStatus
from app.localization.texts import get_texts


logger = structlog.get_logger(__name__)

# Ключ в metadata_json платежа: решение по сообщению принимается один раз, повтор вебхука его не меняет.
DECLINE_NOTICE_KEY = 'decline_notice'
NOTICE_SENT = 'sent'
NOTICE_UNDELIVERED = 'undelivered'
# Статусы, по которым пишем. EXPIRED — истёкший счёт, по нему не пишем никогда.
DECLINE_STATUSES = frozenset({'CANCELED', 'FAILED'})
# Событие общего напоминания о брошенной оплате: записав его, не даём воронке через 10 минут
# написать тому же человеку второй раз о том же счёте.
_FUNNEL_ABANDONED_TOPUP_EVENT = 'funnel_abandoned_topup'


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def decide_platega_decline_notice(
    db: AsyncSession,
    payment: PlategaPayment,
    status: str,
    *,
    bot: Any,
    now: datetime | None = None,
) -> tuple[str | None, User | None]:
    """Писать ли человеку об отказе. Вызывать под блокировкой строки платежа, до смены статуса.

    Возвращает ``(решение, человек)``: ``None`` — решение уже принято раньше (повтор вебхука),
    ``'sent'`` — писать, иначе причина, по которой не пишем.
    """
    metadata = getattr(payment, 'metadata_json', None) or {}
    if metadata.get(DECLINE_NOTICE_KEY):
        return None, None
    if status not in DECLINE_STATUSES:
        return 'expired', None

    now = now or datetime.now(UTC)
    expires_at = _aware(getattr(payment, 'expires_at', None))
    if expires_at is None or now >= expires_at:
        # Счёт дожил до конца срока: отказ от истечения не отличить — молчим.
        return 'expired', None
    if not metadata.get('invoice_message'):
        # Счёт создан не в чате с ботом (кабинет, страница): там свой экран результата.
        return 'not_from_bot', None
    if bot is None or not settings.is_notifications_enabled():
        return 'notifications_off', None

    user = await db.get(User, payment.user_id) if payment.user_id else None
    if (
        user is None
        or not user.telegram_id
        or user.status != UserStatus.ACTIVE.value
        or getattr(user, 'restriction_topup', False)
    ):
        return 'no_recipient', None

    newer_invoice = await db.execute(
        select(exists().where(PlategaPayment.user_id == user.id, PlategaPayment.id > payment.id))
    )
    if newer_invoice.scalar():
        # Человек уже создал следующий счёт сам — «не прошла» о старом только собьёт.
        return 'newer_invoice', None

    created_at = _aware(getattr(payment, 'created_at', None))
    if created_at is not None:
        paid_since = await db.execute(
            select(
                exists().where(
                    Transaction.user_id == user.id,
                    Transaction.type == TransactionType.DEPOSIT.value,
                    Transaction.is_completed.is_(True),
                    Transaction.completed_at >= created_at,
                )
            )
        )
        if paid_since.scalar():
            return 'already_paid', None

    return NOTICE_SENT, user


def decline_notice_message(user: User, payment: PlategaPayment) -> tuple[str, InlineKeyboardMarkup]:
    texts = get_texts(user.language)
    rows: list[list[InlineKeyboardButton]] = []
    method_code = payment.payment_method_code
    if settings.is_platega_enabled() and method_code in settings.get_platega_active_methods():
        # Та же сумма тем же способом: обработчик быстрого пополнения сразу выдаёт новый счёт.
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.t('PAYMENT_DECLINED_RETRY', '🔄 Попробовать ещё раз'),
                    callback_data=f'topup_amount|platega_m{method_code}|{payment.amount_kopeks}',
                    style='success',
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.t('PAYMENT_DECLINED_OTHER_METHOD', 'Другой способ оплаты'),
                callback_data='balance_topup',
            )
        ]
    )
    text = texts.t('PAYMENT_DECLINED_TEXT', '❌ <b>Оплата не прошла, деньги не списаны.</b>')
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def send_platega_decline_notice(db: AsyncSession, bot: Any, user: User, payment: PlategaPayment) -> bool:
    """Отправить сообщение об отказе. Решение ``'sent'`` к этому моменту уже записано и закоммичено."""
    user_id = user.id
    try:
        text, keyboard = decline_notice_message(user, payment)
        await bot.send_message(user.telegram_id, text, parse_mode='HTML', reply_markup=keyboard)
    except Exception as error:
        logger.warning('Отказ оплаты: сообщение не доставлено', user_id=user_id, payment_id=payment.id, error=error)
        try:
            payment.metadata_json = {**(payment.metadata_json or {}), DECLINE_NOTICE_KEY: NOTICE_UNDELIVERED}
            await db.commit()
        except Exception as save_error:
            logger.warning('Отказ оплаты: не удалось отметить недоставку', payment_id=payment.id, error=save_error)
        return False

    try:
        db.add(
            SubscriptionEvent(
                user_id=user_id,
                event_type=_FUNNEL_ABANDONED_TOPUP_EVENT,
                message='payment declined notice',
                amount_kopeks=payment.amount_kopeks,
                occurred_at=datetime.now(UTC),
            )
        )
        await db.commit()
    except Exception as error:
        logger.warning('Отказ оплаты: не удалось записать событие', user_id=user_id, error=error)
    logger.info('Отказ оплаты: человеку отправлено сообщение', user_id=user_id, payment_id=payment.id)
    return True
