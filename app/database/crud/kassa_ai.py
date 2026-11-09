"""CRUD операции для платежей KassaAI."""

from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import KassaAiPayment


logger = structlog.get_logger(__name__)


async def create_kassa_ai_payment(
    db: AsyncSession,
    *,
    user_id: int | None,
    order_id: str,
    amount_kopeks: int,
    currency: str = 'RUB',
    description: str | None = None,
    payment_url: str | None = None,
    payment_system_id: int | None = None,
    expires_at: datetime | None = None,
    metadata_json: dict | None = None,
) -> KassaAiPayment:
    """Создает запись о платеже KassaAI."""
    payment = KassaAiPayment(
        user_id=user_id,
        order_id=order_id,
        amount_kopeks=amount_kopeks,
        currency=currency,
        description=description,
        payment_url=payment_url,
        payment_system_id=payment_system_id,
        expires_at=expires_at,
        metadata_json=metadata_json,
        status='pending',
        is_paid=False,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    logger.info('Создан платеж KassaAI', order_id=order_id, user_id=user_id)
    return payment


async def get_kassa_ai_payment_by_order_id(db: AsyncSession, order_id: str) -> KassaAiPayment | None:
    """Получает платеж по order_id."""
    result = await db.execute(select(KassaAiPayment).where(KassaAiPayment.order_id == order_id))
    return result.scalar_one_or_none()


async def get_kassa_ai_payment_by_id(db: AsyncSession, payment_id: int) -> KassaAiPayment | None:
    """Получает платеж по ID."""
    result = await db.execute(select(KassaAiPayment).where(KassaAiPayment.id == payment_id))
    return result.scalar_one_or_none()


async def get_kassa_ai_payment_by_id_for_update(db: AsyncSession, payment_id: int) -> KassaAiPayment | None:
    result = await db.execute(
        select(KassaAiPayment)
        .where(KassaAiPayment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()
