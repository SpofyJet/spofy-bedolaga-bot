"""Revalidate automatic renewal against locked, current account/subscription data."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Subscription, User
from app.utils.subscription_time import ends_within_days


@dataclass(frozen=True)
class AutopayLock:
    """Результат проверки: ``skip_reason is None`` — продлевать можно, строки заблокированы.

    Иначе блокировки уже сняты commit'ом, а ``skip_reason``:

    * ``'tariff_inactive'`` — всё остальное в порядке, но тариф подписки отключён:
      автопродление молча не сработает, человеку нужно выбрать тариф;
    * ``'not_eligible'`` — штатный пропуск (продлили вручную, выключили
      автопродление, заблокирован, не то окно и т.п.).
    """

    user: User | None
    subscription: Subscription | None
    skip_reason: str | None


async def lock_autopay_target_checked(
    db: AsyncSession,
    user_id: int,
    subscription_id: int,
    *,
    expected_end_date: datetime,
    expired_only: bool = False,
) -> AutopayLock:
    """Hold User then Subscription until caller commits the whole renewal.

    The candidate list and ORM identity map may predate a manual renewal,
    consent change, transfer or block. Recheck them before computing a price.
    """
    from app.database.crud.user import lock_user_for_pricing

    user = await lock_user_for_pricing(db, user_id)
    subscription = await db.scalar(
        select(Subscription)
        .where(Subscription.id == subscription_id, Subscription.user_id == user_id)
        .options(selectinload(Subscription.tariff))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = datetime.now(UTC)
    skip_reason = 'not_eligible'
    if subscription is not None:
        tariff = subscription.tariff
        eligible = (
            user.status == 'active'
            and subscription.autopay_enabled is True
            and (subscription.is_trial is False)
            and (subscription.end_date == expected_end_date)
            and (not subscription.is_daily_paused)
            and (not (tariff and tariff.is_daily))
            and (bool(subscription.tariff_id))
        )
        if expired_only:
            eligible = (
                eligible
                and subscription.status == 'expired'
                and now >= subscription.end_date
                and (now - subscription.end_date).days <= 30
            )
        else:
            eligible = (
                eligible
                and (
                    subscription.status == 'active'
                    or (subscription.status == 'expired' and subscription.end_date >= now - timedelta(hours=2))
                )
                and ends_within_days(subscription.end_date, min(subscription.autopay_days_before or 3, 3), now)
            )
        if eligible and tariff and not tariff.is_active:
            skip_reason = 'tariff_inactive'
        elif eligible:
            return AutopayLock(user, subscription, None)
    # No billing mutations have occurred: release the read locks without
    # expiring the caller's user object (used by the top-up response).
    await db.commit()
    return AutopayLock(user, subscription, skip_reason)


async def lock_autopay_target(
    db: AsyncSession,
    user_id: int,
    subscription_id: int,
    *,
    expected_end_date: datetime,
    expired_only: bool = False,
) -> tuple[User, Subscription] | None:
    """Обёртка для вызывающих, которым причина пропуска не нужна."""
    result = await lock_autopay_target_checked(
        db, user_id, subscription_id, expected_end_date=expected_end_date, expired_only=expired_only
    )
    if result.skip_reason is not None:
        return None
    return result.user, result.subscription
