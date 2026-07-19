from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import XRocketPayment


logger = structlog.get_logger(__name__)


async def create_xrocket_payment(
    db: AsyncSession,
    user_id: int | None,
    invoice_id: str,
    amount: str,
    asset: str,
    amount_kopeks: int = 0,
    fiat_rate: str | None = None,
    status: str = 'active',
    description: str | None = None,
    payload: str | None = None,
    pay_url: str | None = None,
) -> XRocketPayment:
    payment = XRocketPayment(
        user_id=user_id,
        invoice_id=invoice_id,
        amount=amount,
        asset=asset,
        amount_kopeks=amount_kopeks,
        fiat_rate=fiat_rate,
        status=status,
        description=description,
        payload=payload,
        pay_url=pay_url,
    )

    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    logger.info(
        'Создан xRocket платеж',
        invoice_id=invoice_id,
        amount=amount,
        asset=asset,
        user_id=user_id,
    )
    return payment


async def get_xrocket_payment_by_invoice_id(db: AsyncSession, invoice_id: str) -> XRocketPayment | None:
    result = await db.execute(
        select(XRocketPayment)
        .options(selectinload(XRocketPayment.user))
        .where(XRocketPayment.invoice_id == invoice_id)
    )
    return result.scalar_one_or_none()


async def get_xrocket_payment_by_id(db: AsyncSession, payment_id: int) -> XRocketPayment | None:
    result = await db.execute(
        select(XRocketPayment).options(selectinload(XRocketPayment.user)).where(XRocketPayment.id == payment_id)
    )
    return result.scalar_one_or_none()


async def get_xrocket_payment_by_invoice_id_for_update(db: AsyncSession, invoice_id: str) -> XRocketPayment | None:
    result = await db.execute(
        select(XRocketPayment)
        .options(selectinload(XRocketPayment.user))
        .where(XRocketPayment.invoice_id == invoice_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_xrocket_payment_by_id_for_update(db: AsyncSession, payment_id: int) -> XRocketPayment | None:
    result = await db.execute(
        select(XRocketPayment)
        .where(XRocketPayment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def update_xrocket_payment_status(
    db: AsyncSession,
    invoice_id: str,
    status: str,
    paid_at: datetime | None = None,
    *,
    commit: bool = True,
) -> XRocketPayment | None:
    payment = await get_xrocket_payment_by_invoice_id(db, invoice_id)

    if not payment:
        return None

    payment.status = status
    payment.updated_at = datetime.now(UTC)

    if status == 'paid' and paid_at:
        payment.paid_at = paid_at

    if commit:
        await db.commit()
        await db.refresh(payment)
    else:
        await db.flush()

    logger.info('Обновлен статус xRocket платежа', invoice_id=invoice_id, status=status)
    return payment


async def link_xrocket_payment_to_transaction(
    db: AsyncSession, invoice_id: str, transaction_id: int
) -> XRocketPayment | None:
    payment = await get_xrocket_payment_by_invoice_id(db, invoice_id)

    if not payment:
        return None

    payment.transaction_id = transaction_id
    payment.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(payment)

    logger.info('Связан xRocket платеж с транзакцией', invoice_id=invoice_id, transaction_id=transaction_id)
    return payment


async def get_user_xrocket_payments(
    db: AsyncSession, user_id: int, limit: int = 50, offset: int = 0
) -> list[XRocketPayment]:
    result = await db.execute(
        select(XRocketPayment)
        .where(XRocketPayment.user_id == user_id)
        .order_by(XRocketPayment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def get_pending_xrocket_payments(db: AsyncSession, older_than_hours: int = 24) -> list[XRocketPayment]:
    cutoff_time = datetime.now(UTC) - timedelta(hours=older_than_hours)

    result = await db.execute(
        select(XRocketPayment)
        .options(selectinload(XRocketPayment.user))
        .where(and_(XRocketPayment.status == 'active', XRocketPayment.created_at < cutoff_time))
        .order_by(XRocketPayment.created_at)
    )
    return result.scalars().all()
