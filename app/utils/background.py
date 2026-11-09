"""Запуск фоновых задач asyncio без потери ссылки на них."""

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog


logger = structlog.get_logger(__name__)

_running_tasks: set[asyncio.Task[Any]] = set()


def _on_task_done(task: asyncio.Task[Any]) -> None:
    _running_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error('Фоновая задача завершилась ошибкой', task=task.get_name(), error=task.exception())


def spawn_background_task(coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Как ``asyncio.create_task``, но цикл событий не потеряет задачу при сборке мусора."""
    task = asyncio.create_task(coroutine)
    _running_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task
