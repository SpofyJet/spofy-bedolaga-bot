"""Итог активации подарка: до какого числа теперь действует подписка."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.lifetime import is_lifetime_end
from app.utils.timezone import format_local_datetime


async def gift_valid_until_line(db: AsyncSession, texts, user_id: int) -> str:
    """Строка «Подписка действует до …» по фактической дате окончания.

    Остаток прежней подписки при подарке другого тарифа пересчитывается по
    стоимости, поэтому «30 дн.» из подарка итогового срока не показывает.
    Если подписку прочитать не удалось — прежнее «Ваша подписка обновлена.».
    """
    from app.database.crud.subscription import get_subscription_by_user_id

    fallback = texts.t('GIFT_ACTIVATION_UPDATED_LINE', 'Ваша подписка обновлена.')
    try:
        subscription = await get_subscription_by_user_id(db, user_id)
    except Exception:
        return fallback
    end_date = getattr(subscription, 'end_date', None)
    if end_date is None:
        return fallback
    if is_lifetime_end(end_date):
        return texts.t('GIFT_ACTIVATION_VALID_FOREVER', 'Подписка действует навсегда.')
    return texts.t('GIFT_ACTIVATION_VALID_UNTIL', 'Подписка действует до {end_date}.').format(
        end_date=format_local_datetime(end_date, '%d.%m.%Y')
    )


async def subscription_end_fields(db: AsyncSession, user_id: int) -> dict:
    """``end_date`` и ``is_lifetime`` подписки после активации — для ответов кабинета."""
    from app.database.crud.subscription import get_subscription_by_user_id

    try:
        subscription = await get_subscription_by_user_id(db, user_id)
    except Exception:
        return {}
    end_date = getattr(subscription, 'end_date', None)
    if end_date is None:
        return {}
    return {'end_date': end_date, 'is_lifetime': is_lifetime_end(end_date)}
