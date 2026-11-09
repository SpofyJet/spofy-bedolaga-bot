from datetime import UTC, date, datetime
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
