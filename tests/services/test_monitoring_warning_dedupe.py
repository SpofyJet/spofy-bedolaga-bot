"""Предупреждения о трафике / низком балансе и напоминания о сроке.

* Redis недоступен — «уже предупредили» помнит память процесса, а не шлём каждый час.
* Человек заблокировал бота — запоминаем и больше не стучимся каждый цикл.
* Напоминания о сроке не делают по несколько запросов на каждую подписку.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import event

import app.services.monitoring_service as monitoring_module
from app.config import settings
from app.database.models import Base, Subscription, SubscriptionStatus, User
from app.services.notification_settings_service import NotificationSettingsService
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(NotificationSettingsService, 'are_notifications_globally_enabled', staticmethod(lambda: True))
    monkeypatch.setattr('app.services.user_reminders.dispatcher.is_quiet_time', lambda *a, **kw: False)
    # Redis «лежит»: чтение ничего не находит, запись не проходит.
    monkeypatch.setattr(monitoring_module.cache, 'get', AsyncMock(return_value=None))
    monkeypatch.setattr(monitoring_module.cache, 'set', AsyncMock(return_value=False))


def _service(bot) -> monitoring_module.MonitoringService:
    service = monitoring_module.MonitoringService.__new__(monitoring_module.MonitoringService)
    service.bot = bot
    service._notified_users = set()
    service._autopay_fail_state = {}
    return service


def _user(user_id: int, **extra) -> User:
    return User(
        id=user_id,
        telegram_id=1000 + user_id,
        first_name='U',
        language='ru',
        status='active',
        balance_kopeks=extra.pop('balance_kopeks', 0),
        **extra,
    )


def _subscription(sub_id: int, user_id: int, **extra) -> Subscription:
    now = datetime.now(UTC)
    values = {
        'status': SubscriptionStatus.ACTIVE.value,
        'is_trial': False,
        'start_date': now - timedelta(days=20),
        'end_date': now + timedelta(days=10),
        'traffic_limit_gb': 100,
        'traffic_used_gb': 90.0,
        'device_limit': 1,
        'connected_squads': [],
    }
    values.update(extra)
    return Subscription(id=sub_id, remnawave_short_id=f's{sub_id}', user_id=user_id, **values)


@pytest.mark.asyncio
async def test_traffic_warning_sent_once_when_redis_is_down(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock())
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all([_user(1), _subscription(10, 1)])
        await db.commit()
        service = _service(bot)

        await service._check_traffic_warnings(db)
        await service._check_traffic_warnings(db)

    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocked_user_is_not_retried_every_cycle(monkeypatch):
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=TelegramForbiddenError(method=MagicMock(), message='Forbidden: bot was blocked by the user')
        )
    )
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all([_user(1), _subscription(10, 1)])
        await db.commit()
        service = _service(bot)

        await service._check_traffic_warnings(db)
        await service._check_traffic_warnings(db)

    assert bot.send_message.await_count == 1
    # Отметка ушла и в Redis (переживает рестарт, если Redis жив).
    keys = [call.args[0] for call in monitoring_module.cache.set.await_args_list]
    assert monitoring_module.telegram_blocked_cache_key(1001) in keys


@pytest.mark.asyncio
async def test_local_mark_expires(monkeypatch):
    service = _service(None)
    clock = [1000.0]
    monkeypatch.setattr(monitoring_module.time, 'monotonic', lambda: clock[0])

    await service._set_mark('k', 60)
    assert await service._is_marked('k')
    clock[0] += 61
    assert not await service._is_marked('k')
    service._purge_local_marks()
    assert service._local_marks == {}


@pytest.mark.asyncio
async def test_low_balance_alert_sent_once_when_redis_is_down(monkeypatch):
    class _Noon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(monitoring_module, 'datetime', _Noon)
    bot = SimpleNamespace(send_message=AsyncMock())
    async with memory_session(monkeypatch, TABLES) as db:
        user = _user(1, notification_settings={'balance_low_enabled': True, 'balance_low_threshold': 10000})
        db.add_all(
            [
                user,
                _subscription(
                    10,
                    1,
                    autopay_enabled=True,
                    end_date=datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        await db.commit()
        service = _service(bot)

        await service._check_low_balance_alerts(db)
        await service._check_low_balance_alerts(db)

    bot.send_message.assert_awaited_once()


async def _expiring_run_queries(monkeypatch, count: int) -> tuple[int, int]:
    """(сколько напоминаний ушло в первый проход, запросов во втором проходе)."""
    monkeypatch.setattr(settings, 'AUTOPAY_WARNING_DAYS', '3,1')
    async with memory_session(monkeypatch, TABLES) as db:
        rows: list = []
        for index in range(1, count + 1):
            rows.append(_user(index))
            rows.append(_subscription(index, index, end_date=datetime.now(UTC) + timedelta(days=2)))
        db.add_all(rows)
        await db.commit()

        service = _service(SimpleNamespace())
        service._send_subscription_expiring_notification = AsyncMock(return_value=True)
        service._log_monitoring_event = AsyncMock()

        await service._check_expiring_subscriptions(db)
        sent = service._send_subscription_expiring_notification.await_count

        statements: list[str] = []
        engine = db.bind.sync_engine
        listener = lambda conn, cursor, statement, *args: statements.append(statement)  # noqa: E731
        event.listen(engine, 'before_cursor_execute', listener)
        try:
            await service._check_expiring_subscriptions(db)
        finally:
            event.remove(engine, 'before_cursor_execute', listener)
        assert service._send_subscription_expiring_notification.await_count == sent  # второй раз не шлём
    return sent, len(statements)


@pytest.mark.asyncio
async def test_expiring_reminders_query_count_does_not_grow_per_subscription(monkeypatch):
    sent_one, queries_one = await _expiring_run_queries(monkeypatch, 1)
    sent_many, queries_many = await _expiring_run_queries(monkeypatch, 6)

    assert (sent_one, sent_many) == (1, 6)
    assert queries_many == queries_one


@pytest.mark.asyncio
async def test_expiring_reminders_survive_one_broken_subscription(monkeypatch):
    monkeypatch.setattr(settings, 'AUTOPAY_WARNING_DAYS', '3')
    async with memory_session(monkeypatch, TABLES) as db:
        rows: list = []
        for index in (1, 2, 3):
            rows.append(_user(index))
            rows.append(_subscription(index, index, end_date=datetime.now(UTC) + timedelta(days=2)))
        db.add_all(rows)
        await db.commit()

        service = _service(SimpleNamespace())
        sent_to: list[int] = []

        async def send(user, subscription, days, *, has_saved_card=False):
            if subscription.id == 1:
                db.add(_user(2))  # ошибка базы посреди прохода
                await db.flush()
            sent_to.append(subscription.id)
            return True

        service._send_subscription_expiring_notification = send
        service._log_monitoring_event = AsyncMock()

        await service._check_expiring_subscriptions(db)

    assert sorted(sent_to) == [2, 3]
