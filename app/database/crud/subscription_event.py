from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SubscriptionEvent


async def create_subscription_event(
    db: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    subscription_id: int | None = None,
    transaction_id: int | None = None,
    amount_kopeks: int | None = None,
    currency: str | None = None,
    message: str | None = None,
    occurred_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> SubscriptionEvent:
    event = SubscriptionEvent(
        user_id=user_id,
        event_type=event_type,
        subscription_id=subscription_id,
        transaction_id=transaction_id,
        amount_kopeks=amount_kopeks,
        currency=currency,
        message=message,
        occurred_at=occurred_at or datetime.now(UTC),
        extra=extra or None,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
