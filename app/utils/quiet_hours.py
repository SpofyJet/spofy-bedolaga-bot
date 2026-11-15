"""Тихие часы: ночью бот не шлёт несрочные уведомления.

Окно задают USER_REMINDERS_QUIET_HOURS_START / _END (часы по TIMEZONE). Им
пользуются воронка активации, догоняющие письма после окончания подписки и
предупреждения о трафике.
"""

from __future__ import annotations

from datetime import datetime


def is_quiet_time(now: datetime, *, start_hour: int, end_hour: int, tz) -> bool:
    if start_hour == end_hour:
        return False
    hour = now.astimezone(tz).hour
    if start_hour > end_hour:  # через полночь: 21 → 10
        return hour >= start_hour or hour < end_hour
    return start_hour <= hour < end_hour
