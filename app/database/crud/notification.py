import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SentNotification


logger = structlog.get_logger(__name__)


async def notification_sent(
    db: AsyncSession,
    user_id: int,
    subscription_id: int,
    notification_type: str,
    days_before: int | None = None,
) -> bool:
    result = await db.execute(
        select(SentNotification)
        .where(
            SentNotification.user_id == user_id,
            SentNotification.subscription_id == subscription_id,
            SentNotification.notification_type == notification_type,
            SentNotification.days_before == days_before,
        )
        .limit(1)
    )
    return result.scalars().first() is not None


async def list_sent_notification_keys(
    db: AsyncSession,
    subscription_ids,
    notification_type: str,
) -> set[tuple[int, int, int | None]]:
    """Все отметки «уже отправлено» одного типа для пачки подписок одним запросом.

    Ключ — (user_id, subscription_id, days_before), как в ``notification_sent``.
    """
    ids = sorted({int(subscription_id) for subscription_id in subscription_ids})
    if not ids:
        return set()
    keys: set[tuple[int, int, int | None]] = set()
    for start in range(0, len(ids), 1000):
        result = await db.execute(
            select(
                SentNotification.user_id,
                SentNotification.subscription_id,
                SentNotification.days_before,
            ).where(
                SentNotification.notification_type == notification_type,
                SentNotification.subscription_id.in_(ids[start : start + 1000]),
            )
        )
        keys.update((row[0], row[1], row[2]) for row in result.all())
    return keys


async def record_notification(
    db: AsyncSession,
    user_id: int,
    subscription_id: int,
    notification_type: str,
    days_before: int | None = None,
    *,
    commit: bool = True,
) -> None:
    already_exists = await notification_sent(db, user_id, subscription_id, notification_type, days_before)
    if already_exists:
        return
    notification = SentNotification(
        user_id=user_id,
        subscription_id=subscription_id,
        notification_type=notification_type,
        days_before=days_before,
    )
    db.add(notification)
    if commit:
        await db.commit()


async def clear_notifications(db: AsyncSession, subscription_id: int, *, commit: bool = True) -> None:
    await db.execute(delete(SentNotification).where(SentNotification.subscription_id == subscription_id))
    if commit:
        await db.commit()


async def clear_notification_by_type(
    db: AsyncSession,
    subscription_id: int,
    notification_type: str,
    *,
    commit: bool = True,
) -> None:
    await db.execute(
        delete(SentNotification).where(
            SentNotification.subscription_id == subscription_id,
            SentNotification.notification_type == notification_type,
        )
    )
    if commit:
        await db.commit()
