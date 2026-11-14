from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Webhook, WebhookDelivery


async def get_active_webhooks_for_event(
    db: AsyncSession,
    event_type: str,
) -> list[Webhook]:
    """Получить все активные webhooks для конкретного события."""
    result = await db.execute(select(Webhook).where(Webhook.event_type == event_type).where(Webhook.is_active == True))
    return list(result.scalars().all())


async def delete_webhook(db: AsyncSession, webhook: Webhook) -> None:
    """Удалить webhook."""
    await db.delete(webhook)
    await db.commit()


async def record_webhook_delivery(
    db: AsyncSession,
    webhook_id: int,
    event_type: str,
    payload: dict,
    status: str,
    response_status: int | None = None,
    response_body: str | None = None,
    error_message: str | None = None,
    attempt_number: int = 1,
) -> WebhookDelivery:
    """Записать попытку доставки webhook."""
    delivery = WebhookDelivery(
        webhook_id=webhook_id,
        event_type=event_type,
        payload=payload,
        status=status,
        response_status=response_status,
        response_body=response_body,
        error_message=error_message,
        attempt_number=attempt_number,
        delivered_at=datetime.now(UTC) if status == 'success' else None,
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return delivery


async def update_webhook_stats(
    db: AsyncSession,
    webhook: Webhook,
    success: bool,
) -> Webhook:
    """Обновить статистику webhook."""
    if success:
        webhook.success_count += 1
    else:
        webhook.failure_count += 1
    webhook.last_triggered_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(webhook)
    return webhook
