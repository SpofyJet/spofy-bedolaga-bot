"""CRUD operations for CloudPayments payments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CloudPaymentsPayment


logger = structlog.get_logger(__name__)


async def create_cloudpayments_payment(
    db: AsyncSession,
    *,
    user_id: int | None,
    invoice_id: str,
    amount_kopeks: int,
    description: str | None = None,
    currency: str = 'RUB',
    payment_url: str | None = None,
    email: str | None = None,
    metadata: dict[str, Any] | None = None,
    test_mode: bool = False,
) -> CloudPaymentsPayment:
    """
    Create a new CloudPayments payment record.

    Args:
        db: Database session
        user_id: Internal user ID
        invoice_id: Unique invoice ID
        amount_kopeks: Amount in kopeks
        description: Payment description
        currency: Currency code (default RUB)
        payment_url: Payment widget URL
        email: User's email
        metadata: Additional metadata
        test_mode: Whether this is a test payment

    Returns:
        Created CloudPaymentsPayment object
    """
    payment = CloudPaymentsPayment(
        user_id=user_id,
        invoice_id=invoice_id,
        amount_kopeks=amount_kopeks,
        currency=currency,
        description=description,
        status='pending',
        is_paid=False,
        payment_url=payment_url,
        email=email,
        metadata_json=metadata,
        test_mode=test_mode,
    )

    db.add(payment)
    await db.flush()
    await db.refresh(payment)

    logger.debug(
        'Created CloudPayments payment',
        payment_id=payment.id,
        invoice_id=invoice_id,
        amount_kopeks=amount_kopeks,
    )

    return payment


async def get_cloudpayments_payment_by_invoice_id(
    db: AsyncSession,
    invoice_id: str,
) -> CloudPaymentsPayment | None:
    """Get CloudPayments payment by invoice ID."""
    result = await db.execute(select(CloudPaymentsPayment).where(CloudPaymentsPayment.invoice_id == invoice_id))
    return result.scalars().first()


async def get_cloudpayments_payment_by_id(
    db: AsyncSession,
    payment_id: int,
) -> CloudPaymentsPayment | None:
    """Get CloudPayments payment by internal ID."""
    result = await db.execute(select(CloudPaymentsPayment).where(CloudPaymentsPayment.id == payment_id))
    return result.scalars().first()


async def get_cloudpayments_payment_by_id_for_update(
    db: AsyncSession,
    payment_id: int,
) -> CloudPaymentsPayment | None:
    result = await db.execute(
        select(CloudPaymentsPayment).where(CloudPaymentsPayment.id == payment_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def update_cloudpayments_payment(
    db: AsyncSession,
    payment_id: int,
    **kwargs: Any,
) -> CloudPaymentsPayment | None:
    """
    Update CloudPayments payment record.

    Args:
        db: Database session
        payment_id: Internal payment ID
        **kwargs: Fields to update

    Returns:
        Updated payment or None if not found
    """
    payment = await get_cloudpayments_payment_by_id(db, payment_id)
    if not payment:
        return None

    for key, value in kwargs.items():
        if hasattr(payment, key):
            setattr(payment, key, value)

    payment.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(payment)

    return payment
