from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.subscription import decrement_subscription_server_counts
from app.database.models import Subscription, User


logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class TrialActivationReversionResult:
    subscription_rolled_back: bool


async def rollback_trial_subscription_activation(
    db: AsyncSession,
    subscription: Subscription | None,
) -> bool:
    """Удаляет только что созданную триальную подписку; False — если база не дала это сделать."""

    if not subscription:
        return True

    try:
        await decrement_subscription_server_counts(db, subscription)
    except Exception as error:  # pragma: no cover - defensive logging
        logger.error('Failed to decrement server counters during trial rollback', error=error)

    try:
        await db.delete(subscription)
        await db.commit()
    except Exception as error:  # pragma: no cover - defensive logging
        logger.error('Failed to remove trial subscription', subscription_id=subscription.id, error=error)
        await db.rollback()
        return False

    return True


async def revert_trial_activation(
    db: AsyncSession,
    user: User,
    subscription: Subscription | None,
) -> TrialActivationReversionResult:
    """Откатывает триал, если панель не смогла его выдать."""

    rolled_back = await rollback_trial_subscription_activation(db, subscription)

    try:
        await db.refresh(user)
    except Exception as error:  # pragma: no cover - defensive logging
        logger.warning('Failed to refresh user after reverting trial activation', user_id=user.id, error=error)

    return TrialActivationReversionResult(subscription_rolled_back=rolled_back)
