"""Ограниченная FSM-память и контроль RSS процесса.

``MemoryStorage`` из aiogram — безграничный ``defaultdict``: без Redis он
растёт до тех пор, пока не съест память контейнера. ``LimitedMemoryStorage``
ставит потолок (по умолчанию 1024 запись) и вытесняет самые старые записи
FIFO. Патч применяется и при явно переданном storage, и при fallback-значении
по умолчанию — поведение не зависит от выбора вызывающего кода.

RSS берём через ``resource.getrusage`` — без psutil и без чтения ``/proc``,
актуально для Linux-контейнера.
"""

from __future__ import annotations

import resource
from collections import OrderedDict
from typing import Any

import structlog
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage


logger = structlog.get_logger(__name__)

DEFAULT_DATA_LIMIT = 1024

RSS_WARN_MB = 1024
RSS_CHECK_INTERVAL_SEC = 1800


class LimitedMemoryStorage(MemoryStorage):
    """``MemoryStorage`` с потолком записей и FIFO-вытеснением."""

    def __init__(self, data_limit: int = DEFAULT_DATA_LIMIT) -> None:
        if data_limit <= 0:
            raise ValueError('data_limit must be positive')
        self.data_limit = data_limit
        super().__init__()
        # Порядок вставки нужен для FIFO-вытеснения; defaultdict его не хранит.
        self._order: OrderedDict[StorageKey, None] = OrderedDict()
        logger.info('FSM: LimitedMemoryStorage создан', data_limit=data_limit)

    async def set_state(self, key: StorageKey, state: Any = None) -> None:
        self._touch(key)
        await super().set_state(key, state)

    async def get_state(self, key: StorageKey) -> str | None:
        state = await super().get_state(key)
        self._refresh(key, empty_untracked=state is None)
        return state

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        self._touch(key)
        await super().set_data(key, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        data = await super().get_data(key)
        self._refresh(key, empty_untracked=not data)
        return data

    def _touch(self, key: StorageKey) -> None:
        """Запись: ключ отслеживается, лимит enforced FIFO-вытеснением."""
        self._order[key] = None
        self._order.move_to_end(key)
        while len(self._order) > self.data_limit:
            oldest, _ = self._order.popitem(last=False)
            self.storage.pop(oldest, None)
            logger.warning('FSM: вытеснена самая старая запись (лимит памяти)', data_limit=self.data_limit)

    def _refresh(self, key: StorageKey, empty_untracked: bool = False) -> None:
        """Чтение: живую запись молодим, вытесненную не воскрешаем.

        Без этого чтение вытесненного ключа возвращало бы его в очередь и
        вытесняло чужую живую запись, а defaultdict super() оставлял бы
        пустой недоучтённый record — память росла бы мимо лимита.
        """
        if key in self._order:
            self._order.move_to_end(key)
        elif empty_untracked:
            self.storage.pop(key, None)


def current_rss_mb() -> float:
    """Текущий RSS процесса в мегабайтах (Linux, без зависимостей)."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux отдаёт килобайты, macOS — байты; в контейнере всегда Linux.
    return round(usage / 1024, 1)


def log_memory(prefix: str = 'memory') -> None:
    """Одна строка в лог с RSS; предупреждение при превышении порога."""
    rss = current_rss_mb()
    if rss > RSS_WARN_MB:
        logger.warning(f'{prefix}: RSS выше порога', rss_mb=rss, threshold_mb=RSS_WARN_MB)
    else:
        logger.info(f'{prefix}: RSS', rss_mb=rss)
