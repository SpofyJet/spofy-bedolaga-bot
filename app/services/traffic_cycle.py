"""Месячный цикл трафика от дня покупки.

День сброса — день покупки подписки. Продление и смена тарифа его не трогают,
покупка после окончания подписки задаёт новый.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


MODE = 'SUBSCRIPTION_MONTH'


def begin_traffic_cycle(subscription, now: datetime | None = None) -> None:
    """Новая покупка: отсчёт начинается заново."""
    subscription.traffic_cycle_anchor_at = now or datetime.now(UTC)


def keep_traffic_cycle(subscription) -> None:
    """Запомнить день сброса перед тем, как изменится ``start_date``."""
    if subscription.traffic_cycle_anchor_at is None:
        subscription.traffic_cycle_anchor_at = subscription.start_date


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def latest_cycle_date(anchor: date, today: date) -> date | None:
    """Последний день сброса не позже ``today``. ``None`` — первого месяца ещё не прошло."""
    candidate = _clamped(today.year, today.month, anchor.day)
    if candidate > today:
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        candidate = _clamped(year, month, anchor.day)
    return candidate if candidate > anchor else None


def is_cycle_due(anchor_at: datetime, last_reset_at: datetime | None, now: datetime, tz: ZoneInfo) -> bool:
    due = latest_cycle_date(anchor_at.astimezone(tz).date(), now.astimezone(tz).date())
    if due is None:
        return False
    return last_reset_at is None or last_reset_at.astimezone(tz).date() < due


def next_cycle_date(anchor: date, today: date) -> date:
    """Первый день сброса строго после ``today``."""
    year, month = today.year, today.month
    while True:
        candidate = _clamped(year, month, anchor.day)
        if candidate > today and candidate > anchor:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def next_reset_at(anchor_at: datetime, last_reset_at: datetime | None, now: datetime, tz: ZoneInfo) -> datetime:
    """Начало (в UTC) местного дня, когда счётчик обнулится в следующий раз.

    Если сброс положен уже сегодня, но проход его ещё не выполнил, это сегодняшний день.
    """
    anchor, today = anchor_at.astimezone(tz).date(), now.astimezone(tz).date()
    if is_cycle_due(anchor_at, last_reset_at, now, tz):
        day = latest_cycle_date(anchor, today)
    else:
        day = next_cycle_date(anchor, today)
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
