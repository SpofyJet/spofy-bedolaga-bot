"""Тихие часы: окно через полночь и одинаковые границы."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.utils.quiet_hours import is_quiet_time


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ('hour', 'quiet'), [(9, True), (10, False), (15, False), (20, False), (21, True), (23, True), (3, True)]
)
def test_quiet_hours_wrap_midnight(hour, quiet):
    now = datetime(2026, 9, 22, hour, 30, tzinfo=UTC)
    assert is_quiet_time(now, start_hour=21, end_hour=10, tz=ZoneInfo('UTC')) is quiet


def test_equal_hours_mean_no_quiet_time():
    assert is_quiet_time(NOW, start_hour=0, end_hour=0, tz=ZoneInfo('UTC')) is False
