"""Ежемесячный сброс трафика в день покупки подписки.

Панель умеет считать месяц только от своей даты создания пользователя, поэтому
в панели стоит NO_RESET, а счётчик обнуляет этот проход.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database.crud.subscription import reactivate_subscription, update_subscription_usage
from app.database.models import Subscription, SubscriptionStatus, Tariff
from app.services.traffic_cycle import MODE, is_cycle_due, next_reset_at
from app.utils.timezone import get_local_timezone


logger = structlog.get_logger(__name__)

_INTERVAL_SECONDS = 3600
_PAUSE_SECONDS = 0.3
_LIVE_STATUSES = (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.LIMITED.value)


def _uses_cycle(tariff_mode: str | None) -> bool:
    return (tariff_mode or settings.DEFAULT_TRAFFIC_RESET_STRATEGY or '').upper() == MODE


def next_traffic_reset_at(subscription: Subscription, now: datetime | None = None) -> datetime | None:
    """Когда этот проход обнулит трафик подписки в следующий раз; ``None`` — сброса не будет.

    Условия те же, что в ``_due_ids``: живая платная подписка с лимитом трафика на
    тарифе с циклом от дня покупки. Если подписка закончится раньше — тоже ``None``.
    """
    now = now or datetime.now(UTC)
    if subscription.is_trial or (subscription.traffic_limit_gb or 0) <= 0:
        return None
    if subscription.status not in _LIVE_STATUSES or subscription.end_date is None or subscription.end_date <= now:
        return None
    tariff = subscription.tariff if subscription.tariff_id else None
    if not _uses_cycle(tariff.traffic_reset_mode if tariff else None):
        return None
    anchor = subscription.traffic_cycle_anchor_at or subscription.start_date
    if anchor is None:
        return None
    moment = next_reset_at(anchor, subscription.traffic_cycle_reset_at, now, get_local_timezone())
    return moment if moment < subscription.end_date else None


class TrafficCycleService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name='traffic-cycle')

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        while True:
            try:
                stats = await self.run_once()
                if any(stats.values()):
                    logger.info('Сброс трафика от дня покупки', **stats)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error('Сброс трафика: ошибка прохода', error=str(error), exc_info=True)
            await asyncio.sleep(_INTERVAL_SECONDS)

    async def _due_ids(self, db) -> list[int]:
        now = datetime.now(UTC)
        tz = get_local_timezone()
        rows = await db.execute(
            select(
                Subscription.id,
                Subscription.traffic_cycle_anchor_at,
                Subscription.start_date,
                Subscription.traffic_cycle_reset_at,
                Tariff.traffic_reset_mode,
            )
            .outerjoin(Tariff, Tariff.id == Subscription.tariff_id)
            .where(
                Subscription.status.in_(_LIVE_STATUSES),
                Subscription.is_trial.is_(False),
                Subscription.traffic_limit_gb > 0,
                Subscription.end_date > now,
            )
        )
        return [
            row.id
            for row in rows
            if _uses_cycle(row.traffic_reset_mode)
            and (row.traffic_cycle_anchor_at or row.start_date) is not None
            and is_cycle_due(row.traffic_cycle_anchor_at or row.start_date, row.traffic_cycle_reset_at, now, tz)
        ]

    async def run_once(self) -> dict[str, int]:
        from app.database.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            ids = await self._due_ids(db)

        stats = {'reset': 0, 'failed': 0, 'skipped': 0}
        for subscription_id in ids:
            try:
                async with AsyncSessionLocal() as db:
                    stats['reset' if await self._reset_one(db, subscription_id) else 'skipped'] += 1
            except asyncio.CancelledError:
                raise
            except Exception as error:
                stats['failed'] += 1
                logger.warning('Сброс трафика не удался', subscription_id=subscription_id, error=str(error))
            await asyncio.sleep(_PAUSE_SECONDS)
        return stats

    @staticmethod
    async def _load(db, subscription_id: int, *, lock: bool) -> Subscription | None:
        query = (
            select(Subscription)
            .where(Subscription.id == subscription_id)
            .options(selectinload(Subscription.user), selectinload(Subscription.tariff))
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update(of=Subscription)
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    def _panel_user_id_if_due(subscription: Subscription | None, now: datetime) -> str | None:
        """UUID в панели, если подписке сейчас положен сброс; иначе None."""
        if subscription is None or subscription.status not in _LIVE_STATUSES or subscription.end_date <= now:
            return None
        anchor = subscription.traffic_cycle_anchor_at or subscription.start_date
        if anchor is None or not is_cycle_due(anchor, subscription.traffic_cycle_reset_at, now, get_local_timezone()):
            return None
        if settings.is_multi_tariff_enabled():
            return subscription.remnawave_id or None
        return subscription.user.remnawave_id or None

    async def _reset_one(self, db, subscription_id: int) -> bool:
        from app.services.bypass_downgrade_service import bypass_downgrade_service
        from app.services.subscription_service import SubscriptionService
        from app.services.traffic_reset_policy import lift_panel_traffic_limit

        # Сначала запрос в панель, потом блокировка строки: иначе строка подписки
        # заперта на всё время сетевого вызова, и покупка или продление этого же
        # человека ждут ответа панели.
        subscription = await self._load(db, subscription_id, lock=False)
        panel_user_id = self._panel_user_id_if_due(subscription, datetime.now(UTC))
        if not panel_user_id:
            return False
        await db.rollback()

        service = SubscriptionService()
        async with service.get_api_client() as api:
            await api.reset_user_traffic(panel_user_id, enrich=False)

        # Под блокировкой проверяем заново: второй проход или другой экземпляр мог
        # успеть записать сброс, пока шёл запрос.
        subscription = await self._load(db, subscription_id, lock=True)
        now = datetime.now(UTC)
        if not self._panel_user_id_if_due(subscription, now):
            return False
        user = subscription.user

        was_limited = subscription.status == SubscriptionStatus.LIMITED.value
        subscription.traffic_cycle_reset_at = now
        await update_subscription_usage(db, subscription, 0.0)
        if was_limited:
            await reactivate_subscription(db, subscription)
            await lift_panel_traffic_limit(db, subscription, service=service)
        await bypass_downgrade_service.restore(db, user, subscription, source='traffic_cycle')
        logger.info('Трафик сброшен в день покупки', subscription_id=subscription.id, user_id=subscription.user_id)
        return True


traffic_cycle_service = TrafficCycleService()
