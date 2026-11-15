"""Свежее состояние подписки под блокировкой — для записи в панель.

Проход синхронизации ждёт своей очереди к панели, а за это время продление могло
уже закоммитить новую дату. Поэтому PATCH собирается не из объекта, прочитанного
в начале прохода, а из подписки, перечитанной ПОСЛЕ взятия блокировки, в своей
сессии: несколько задач прохода не делят одну сессию SQLAlchemy.

Раньше это делал ``grace_sensitive_panel_update`` грейс-доступа; грейс удалён,
блокировка и свежее чтение остались.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.database.models import Subscription


class _KeyedLocks:
    """Блокировка в пределах процесса по id подписки."""

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._locks: dict[int, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def hold(self, subscription_id: int):
        async with self._guard:
            lock, users = self._locks.get(subscription_id, (asyncio.Lock(), 0))
            self._locks[subscription_id] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            async with self._guard:
                current_lock, users = self._locks[subscription_id]
                if users <= 1 and not current_lock.locked():
                    self._locks.pop(subscription_id, None)
                else:
                    self._locks[subscription_id] = (current_lock, users - 1)


_locks = _KeyedLocks()


@dataclass(frozen=True)
class SubscriptionLease:
    """Подписка, перечитанная под блокировкой, и сессия, которой она принадлежит."""

    subscription: Subscription | None
    db: AsyncSession

    @property
    def allowed(self) -> bool:
        return self.subscription is not None


@asynccontextmanager
async def subscription_update_lease(subscription_id: int):
    """Держать блокировку подписки и отдать её свежее состояние; коммит — на выходе."""
    async with _locks.hold(subscription_id):
        async with AsyncSessionLocal() as lease_db:
            async with lease_db.begin():
                result = await lease_db.execute(
                    select(Subscription)
                    .options(
                        selectinload(Subscription.user),
                        selectinload(Subscription.tariff),
                    )
                    .execution_options(populate_existing=True)
                    .where(Subscription.id == subscription_id)
                )
                yield SubscriptionLease(subscription=result.scalar_one_or_none(), db=lease_db)
