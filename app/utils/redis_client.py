"""Единая точка создания клиента Redis.

redis-py ≥ 8 по умолчанию (``maint_notifications_config.enabled="auto"``) на каждом
новом соединении шлёт ``CLIENT MAINT_NOTIFICATIONS`` — уведомления о плановых
работах Redis Enterprise. Обычный Redis команду не знает, и библиотека на каждое
соединение пишет в лог «Failed to enable maintenance notifications». Бот с Redis
Enterprise не работает, поэтому механизм выключен явно — но только там, где он
вообще существует.

Важно: в redis-py 7.x async-стек (redis.asyncio) параметр
``maint_notifications_config`` НЕ принимает — передача приводит к TypeError
на первом же запросе (клиент конструируется лениво, импорты этого не ловят).
Поэтому поддержка определяется интроспекцией сигнатуры соединения,
а не номером версии пакета.
"""

from __future__ import annotations

import inspect
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import AbstractConnection

from app.config import settings


try:
    from redis.maint_notifications import MaintNotificationsConfig
except ImportError:  # redis-py без механизма maint_notifications: выключать нечего
    MaintNotificationsConfig = None  # type: ignore[assignment,misc]

_SUPPORTS_MAINT_NOTIFICATIONS = MaintNotificationsConfig is not None and (
    'maint_notifications_config' in inspect.signature(AbstractConnection.__init__).parameters
)


def create_redis(url: str | None = None, **kwargs: Any) -> redis.Redis:
    """Клиент с пулом соединений к ``url`` (по умолчанию ``settings.REDIS_URL``)."""
    if _SUPPORTS_MAINT_NOTIFICATIONS:
        kwargs.setdefault('maint_notifications_config', MaintNotificationsConfig(enabled=False))
    return redis.from_url(url or settings.REDIS_URL, **kwargs)
