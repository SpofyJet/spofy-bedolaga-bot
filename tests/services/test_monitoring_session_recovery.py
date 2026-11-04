"""Сбой базы в одном шаге мониторинга не ломает остальные шаги и подписки.

Шаги цикла мониторинга идут в одной сессии. Раньше внешний ``except`` шага
только логировал ошибку: сессия оставалась «сломанной», и все следующие шаги
(напоминания, трафик, истечения) падали с PendingRollbackError. Суточные
списания: откат после сбоя одной подписки экспайрил загруженный список, и
следующая подписка падала на ленивой подгрузке — за проход обрабатывалась одна.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.database.models import Base, Subscription, SubscriptionStatus, Tariff, User
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


def _user(user_id: int) -> User:
    return User(id=user_id, telegram_id=1000 + user_id, first_name='U', language='ru', status='active')


def _daily_rows() -> list:
    now = datetime.now(UTC)
    rows: list = [
        Tariff(
            id=1,
            name='Сутки',
            description='',
            is_active=True,
            is_daily=True,
            daily_price_kopeks=1000,
            period_prices={},
            traffic_limit_gb=0,
            device_limit=1,
            allowed_squads=[],
            display_order=1,
        )
    ]
    for index in (1, 2, 3):
        rows.append(_user(index))
        rows.append(
            Subscription(
                id=10 + index,
                remnawave_short_id=f's{index}',
                user_id=index,
                status=SubscriptionStatus.ACTIVE.value,
                is_trial=False,
                start_date=now - timedelta(days=1),
                end_date=now - timedelta(minutes=5),
                traffic_limit_gb=0,
                traffic_used_gb=0.0,
                device_limit=1,
                tariff_id=1,
                connected_squads=[],
            )
        )
    return rows


def _monitoring_service():
    import app.services.monitoring_service as monitoring_module

    service = monitoring_module.MonitoringService.__new__(monitoring_module.MonitoringService)
    service.bot = None
    service._notified_users = set()
    service._autopay_fail_state = {}
    return service


@pytest.mark.asyncio
async def test_failed_step_leaves_session_usable_for_next_step(monkeypatch):
    import app.services.monitoring_service as monitoring_module

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(1))
        await db.commit()

        async def broken_query(session):
            # Дубликат первичного ключа: flush падает, сессия требует отката.
            session.add(_user(1))
            await session.flush()

        monkeypatch.setattr(monitoring_module, 'get_expired_subscriptions', broken_query)
        await _monitoring_service()._check_expired_subscriptions(db)

        # Следующий шаг цикла работает в той же сессии.
        users = (await db.execute(select(User.id))).scalars().all()
        assert users == [1]


@pytest.mark.asyncio
async def test_failed_monitoring_log_does_not_break_session(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(1))
        await db.commit()
        db.add(_user(1))  # «чужой» мусор в сессии: commit лога упадёт на flush

        await _monitoring_service()._log_monitoring_event(db, 'test', 'test')

        users = (await db.execute(select(User.id))).scalars().all()
        assert users == [1]


@pytest.mark.asyncio
async def test_daily_charges_continue_after_failed_subscription(monkeypatch):
    import app.services.daily_subscription_service as daily_module

    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(_daily_rows())
        await db.commit()

        async def listed(session):
            result = await session.execute(
                select(Subscription).order_by(Subscription.id).execution_options(populate_existing=True)
            )
            subscriptions = result.scalars().all()
            for subscription in subscriptions:
                await session.refresh(subscription, ['user', 'tariff'])
            return subscriptions

        seen: list[tuple[int, int, str]] = []

        async def charge(session, subscription):
            # Читаем связи так же, как настоящее списание.
            seen.append((subscription.id, subscription.user.id, subscription.tariff.name))
            if subscription.id == 11:
                # Панель недоступна: списание откатывает сессию и падает.
                await session.rollback()
                raise RuntimeError('panel down')
            return 'charged'

        @contextlib.asynccontextmanager
        async def session_factory():
            yield db

        monkeypatch.setattr(daily_module, 'get_daily_subscriptions_for_charge', listed)
        monkeypatch.setattr(daily_module, 'AsyncSessionLocal', session_factory)
        service = daily_module.DailySubscriptionService()
        monkeypatch.setattr(service, '_process_single_charge', charge)

        stats = await service.process_daily_charges()

    assert [item[0] for item in seen] == [11, 12, 13]
    assert stats == {'checked': 3, 'charged': 2, 'suspended': 0, 'errors': 1}


@pytest.mark.asyncio
async def test_daily_charges_skip_subscription_deleted_mid_run(monkeypatch):
    import app.services.daily_subscription_service as daily_module

    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(_daily_rows())
        await db.commit()

        async def listed(session):
            # Выборка вернула подписку, которую удалили до её обработки.
            return [SimpleNamespace(id=99), await session.get(Subscription, 12)]

        @contextlib.asynccontextmanager
        async def session_factory():
            yield db

        monkeypatch.setattr(daily_module, 'get_daily_subscriptions_for_charge', listed)
        monkeypatch.setattr(daily_module, 'AsyncSessionLocal', session_factory)
        service = daily_module.DailySubscriptionService()
        charge = AsyncMock(return_value='charged')
        monkeypatch.setattr(service, '_process_single_charge', charge)

        stats = await service.process_daily_charges()

    assert charge.await_count == 1
    assert stats['charged'] == 1
    assert stats['errors'] == 0
