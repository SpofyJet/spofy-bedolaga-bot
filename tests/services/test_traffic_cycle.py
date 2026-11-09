from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.external.remnawave_api import TrafficLimitStrategy
from app.services.panel_sync.traffic_strategy import get_traffic_reset_strategy
from app.services.traffic_cycle import begin_traffic_cycle, is_cycle_due, keep_traffic_cycle, latest_cycle_date


MSK = ZoneInfo('Europe/Moscow')


@pytest.mark.parametrize(
    ('anchor', 'today', 'expected'),
    [
        (date(2026, 11, 15), date(2026, 11, 20), None),
        (date(2026, 11, 15), date(2026, 12, 14), None),
        (date(2026, 11, 15), date(2026, 12, 15), date(2026, 12, 15)),
        (date(2026, 11, 15), date(2027, 1, 3), date(2026, 12, 15)),
        (date(2026, 1, 31), date(2026, 2, 28), date(2026, 2, 28)),
        (date(2026, 1, 31), date(2026, 2, 27), None),
        (date(2025, 12, 20), date(2026, 1, 5), None),
        (date(2025, 11, 20), date(2026, 1, 5), date(2025, 12, 20)),
    ],
)
def test_latest_cycle_date(anchor, today, expected):
    assert latest_cycle_date(anchor, today) == expected


def test_due_once_per_cycle():
    anchor = datetime(2026, 10, 15, 12, tzinfo=UTC)
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    assert is_cycle_due(anchor, None, now, MSK)
    assert is_cycle_due(anchor, datetime(2026, 10, 20, tzinfo=UTC), now, MSK)
    assert not is_cycle_due(anchor, datetime(2026, 11, 15, 1, tzinfo=UTC), now, MSK)


def test_local_day_decides():
    anchor = datetime(2026, 10, 14, 22, tzinfo=UTC)  # 15-е по Москве
    assert is_cycle_due(anchor, None, datetime(2026, 11, 14, 22, tzinfo=UTC), MSK)
    assert not is_cycle_due(anchor, None, datetime(2026, 11, 14, 20, tzinfo=UTC), MSK)


def test_renewal_keeps_day_and_new_purchase_replaces_it():
    start = datetime(2026, 4, 14, tzinfo=UTC)
    sub = SimpleNamespace(traffic_cycle_anchor_at=None, start_date=start)
    keep_traffic_cycle(sub)
    assert sub.traffic_cycle_anchor_at == start
    sub.start_date = datetime(2026, 6, 1, tzinfo=UTC)
    keep_traffic_cycle(sub)
    assert sub.traffic_cycle_anchor_at == start
    later = datetime(2026, 9, 3, tzinfo=UTC)
    begin_traffic_cycle(sub, later)
    assert sub.traffic_cycle_anchor_at == later


def test_panel_does_not_reset_by_itself():
    tariff = SimpleNamespace(traffic_reset_mode='SUBSCRIPTION_MONTH', name='x')
    assert get_traffic_reset_strategy(tariff) is TrafficLimitStrategy.NO_RESET


class _CycleDb:
    """Сессия-заглушка: запоминает порядок запросов и отдаёт подписку."""

    def __init__(self, events, subscription, *, reset_by_other_worker_at=None):
        self.events = events
        self.subscription = subscription
        self.reset_by_other_worker_at = reset_by_other_worker_at

    async def execute(self, query):
        locked = query._for_update_arg is not None
        self.events.append('select_locked' if locked else 'select')
        if locked and self.reset_by_other_worker_at is not None:
            self.subscription.traffic_cycle_reset_at = self.reset_by_other_worker_at
        return SimpleNamespace(scalar_one_or_none=lambda: self.subscription)

    async def rollback(self):
        self.events.append('rollback')


def _cycle_env(monkeypatch, events):
    from contextlib import asynccontextmanager

    from app.services import bypass_downgrade_service as bypass_module, subscription_service, traffic_cycle_service

    class _Api:
        async def reset_user_traffic(self, panel_user_id, enrich=False):
            events.append(f'panel:{panel_user_id}')

    class _Service:
        @asynccontextmanager
        async def get_api_client(self):
            yield _Api()

    async def _usage(db, subscription, used_gb):
        events.append('write')

    async def _restore(db, user, subscription, source):
        return None

    monkeypatch.setattr(subscription_service, 'SubscriptionService', _Service)
    monkeypatch.setattr(traffic_cycle_service, 'update_subscription_usage', _usage)
    monkeypatch.setattr(bypass_module.bypass_downgrade_service, 'restore', _restore)
    monkeypatch.setattr(type(traffic_cycle_service.settings), 'is_multi_tariff_enabled', lambda self: False)
    return traffic_cycle_service.TrafficCycleService()


def _due_subscription():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=7,
        user_id=3,
        status='active',
        end_date=now + timedelta(days=20),
        start_date=now - timedelta(days=70),
        traffic_cycle_anchor_at=now - timedelta(days=70),
        traffic_cycle_reset_at=None,
        remnawave_id=None,
        user=SimpleNamespace(remnawave_id='panel-uuid'),
    )


def _force_due(monkeypatch):
    from app.services import traffic_cycle_service

    monkeypatch.setattr(traffic_cycle_service, 'is_cycle_due', lambda anchor, reset_at, now, tz: reset_at is None)


async def test_row_is_locked_only_after_the_panel_answered(monkeypatch):
    events = []
    service = _cycle_env(monkeypatch, events)
    _force_due(monkeypatch)
    subscription = _due_subscription()

    assert await service._reset_one(_CycleDb(events, subscription), 7) is True

    assert events == ['select', 'rollback', 'panel:panel-uuid', 'select_locked', 'write']
    assert subscription.traffic_cycle_reset_at is not None


async def test_second_worker_does_not_write_the_reset_twice(monkeypatch):
    events = []
    service = _cycle_env(monkeypatch, events)
    _force_due(monkeypatch)
    other = datetime.now(UTC)
    db = _CycleDb(events, _due_subscription(), reset_by_other_worker_at=other)

    assert await service._reset_one(db, 7) is False

    assert 'write' not in events
    assert db.subscription.traffic_cycle_reset_at == other


async def test_not_due_subscription_never_reaches_the_panel(monkeypatch):
    events = []
    service = _cycle_env(monkeypatch, events)
    _force_due(monkeypatch)
    subscription = _due_subscription()
    subscription.traffic_cycle_reset_at = datetime.now(UTC)

    assert await service._reset_one(_CycleDb(events, subscription), 7) is False

    assert events == ['select']
