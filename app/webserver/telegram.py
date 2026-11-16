from __future__ import annotations

import asyncio
import hmac
import re
import time
from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import settings


logger = structlog.get_logger(__name__)

# Замер ожидания: сколько update стоял в очереди и сколько шла обработка. Раз в STATS_PERIOD — одна строка сводки,
# отдельной строкой — каждый update, который ждал или обрабатывался дольше порога. Идентификаторы людей не пишутся.
STATS_PERIOD_SECONDS = 300.0
SLOW_WAIT_SECONDS = 2.0
SLOW_HANDLE_SECONDS = 5.0
_KIND_CUT = re.compile(r'[:\d]')


def _update_kind(update: Any) -> str:
    """Вид update для журнала: начало callback_data до первой цифры или двоеточия, имя команды; без текста и id."""
    try:
        callback = getattr(update, 'callback_query', None)
        if callback is not None:
            return 'callback:' + _KIND_CUT.split(callback.data or '', maxsplit=1)[0][:40]
        message = getattr(update, 'message', None)
        if message is not None:
            text = message.text or ''
            if text.startswith('/'):
                return 'command:' + text.split()[0].split('@')[0][:20]
            return 'message'
        return str(getattr(update, 'event_type', 'other'))
    except Exception:  # pragma: no cover - замер не должен мешать обработке
        return 'other'


def _percentile(values: list[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))]


class TelegramWebhookProcessorError(RuntimeError):
    """Базовое исключение очереди Telegram webhook."""


class TelegramWebhookProcessorNotRunningError(TelegramWebhookProcessorError):
    """Очередь ещё не запущена или уже остановлена."""


class TelegramWebhookOverloadedError(TelegramWebhookProcessorError):
    """Очередь переполнена и не успевает обрабатывать новые обновления."""


class TelegramWebhookProcessor:
    """Асинхронная очередь обработки Telegram webhook-ов."""

    active: TelegramWebhookProcessor | None = None  # запущенная очередь: по ней живое меню видит нагрузку

    def __init__(
        self,
        *,
        bot: Bot,
        dispatcher: Dispatcher,
        queue_maxsize: int,
        worker_count: int,
        enqueue_timeout: float,
        shutdown_timeout: float,
    ) -> None:
        self._bot = bot
        self._dispatcher = dispatcher
        self._queue_maxsize = max(1, queue_maxsize)
        self._worker_count = max(0, worker_count)
        self._enqueue_timeout = max(0.0, enqueue_timeout)
        self._shutdown_timeout = max(1.0, shutdown_timeout)
        self._queue: asyncio.Queue[tuple[Update, float] | object] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._busy = 0
        self._reset_stats()
        self._workers: list[asyncio.Task[None]] = []
        self._running = False
        self._stop_sentinel: object = object()
        self._lifecycle_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def _reset_stats(self) -> None:
        self._stats_started = time.monotonic()
        self._waits: list[float] = []
        self._handles: list[float] = []
        self._busy_max = 0
        self._queue_max = 0

    def _record(self, update: Any, wait: float, handle: float) -> None:
        try:
            self._waits.append(wait)
            self._handles.append(handle)
            if wait >= SLOW_WAIT_SECONDS or handle >= SLOW_HANDLE_SECONDS:
                logger.warning(
                    'Медленный Telegram update',
                    kind=_update_kind(update),
                    wait_ms=round(wait * 1000),
                    handle_ms=round(handle * 1000),
                    queue=self._queue.qsize(),
                    busy=self._busy,
                )
            if time.monotonic() - self._stats_started >= STATS_PERIOD_SECONDS:
                logger.info(
                    'Очередь Telegram webhook: сводка',
                    updates=len(self._waits),
                    wait_p50_ms=round(_percentile(self._waits, 0.5) * 1000),
                    wait_p95_ms=round(_percentile(self._waits, 0.95) * 1000),
                    wait_max_ms=round(max(self._waits) * 1000),
                    waited_over_1s=sum(1 for value in self._waits if value >= 1.0),
                    handle_p50_ms=round(_percentile(self._handles, 0.5) * 1000),
                    handle_p95_ms=round(_percentile(self._handles, 0.95) * 1000),
                    handle_max_ms=round(max(self._handles) * 1000),
                    busy_max=self._busy_max,
                    queue_max=self._queue_max,
                    workers=self._worker_count,
                )
                self._reset_stats()
        except Exception:  # pragma: no cover - замер не должен мешать обработке
            self._reset_stats()

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._running:
                return

            self._running = True
            TelegramWebhookProcessor.active = self
            self._queue = asyncio.Queue(maxsize=self._queue_maxsize)
            self._workers.clear()

            for index in range(self._worker_count):
                task = asyncio.create_task(
                    self._worker_loop(index),
                    name=f'telegram-webhook-worker-{index}',
                )
                self._workers.append(task)

            if self._worker_count:
                logger.info(
                    '🚀 Telegram webhook processor запущен',
                    worker_count=self._worker_count,
                    queue_maxsize=self._queue_maxsize,
                )
            else:
                logger.warning('Telegram webhook processor запущен без воркеров — обновления не будут обрабатываться')

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            if not self._running:
                return

            self._running = False

            if self._worker_count > 0:
                try:
                    await asyncio.wait_for(self._queue.join(), timeout=self._shutdown_timeout)
                except TimeoutError:
                    logger.warning(
                        '⏱️ Не удалось дождаться завершения очереди Telegram webhook',
                        shutdown_timeout=self._shutdown_timeout,
                    )
            else:
                drained = 0
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except asyncio.QueueEmpty:  # pragma: no cover - гонка состояния
                        break
                    else:
                        drained += 1
                        self._queue.task_done()
                if drained:
                    logger.warning('Очередь Telegram webhook остановлена без воркеров', drained=drained)

            for _ in range(len(self._workers)):
                try:
                    self._queue.put_nowait(self._stop_sentinel)
                except asyncio.QueueFull:
                    # Очередь переполнена, подождём пока освободится место
                    await self._queue.put(self._stop_sentinel)

            if self._workers:
                await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
            logger.info('🛑 Telegram webhook processor остановлен')

    async def enqueue(self, update: Update) -> None:
        if not self._running:
            raise TelegramWebhookProcessorNotRunningError

        try:
            item = (update, time.monotonic())
            if self._enqueue_timeout <= 0:
                self._queue.put_nowait(item)
            else:
                await asyncio.wait_for(self._queue.put(item), timeout=self._enqueue_timeout)
            self._queue_max = max(self._queue_max, self._queue.qsize())
        except asyncio.QueueFull as error:  # pragma: no cover - защитный сценарий
            raise TelegramWebhookOverloadedError from error
        except TimeoutError as error:
            raise TelegramWebhookOverloadedError from error

    async def _worker_loop(self, worker_id: int) -> None:
        try:
            while True:
                try:
                    item = await self._queue.get()
                except asyncio.CancelledError:  # pragma: no cover - остановка приложения
                    logger.debug('Worker cancelled', worker_id=worker_id)
                    raise

                if item is self._stop_sentinel:
                    self._queue.task_done()
                    break

                update, enqueued_at = item  # type: ignore[misc]
                started_at = time.monotonic()
                self._busy += 1
                self._busy_max = max(self._busy_max, self._busy)
                try:
                    await self._dispatcher.feed_update(self._bot, update)  # type: ignore[arg-type]
                except asyncio.CancelledError:  # pragma: no cover - остановка приложения
                    logger.debug('Worker cancelled during processing', worker_id=worker_id)
                    raise
                except Exception as error:  # pragma: no cover - логируем сбой обработчика
                    logger.exception('Ошибка обработки Telegram update в worker', worker_id=worker_id, error=error)
                finally:
                    self._busy -= 1
                    self._record(update, started_at - enqueued_at, time.monotonic() - started_at)
                    self._queue.task_done()
        finally:
            logger.debug('Worker завершён', worker_id=worker_id)


async def _dispatch_update(
    update: Update,
    *,
    dispatcher: Dispatcher,
    bot: Bot,
    processor: TelegramWebhookProcessor | None,
) -> None:
    if processor is not None:
        try:
            await processor.enqueue(update)
        except TelegramWebhookOverloadedError as error:
            logger.warning('Очередь Telegram webhook переполнена', error=error)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='webhook_queue_full') from error
        except TelegramWebhookProcessorNotRunningError as error:
            logger.error('Telegram webhook processor неактивен', error=error)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='webhook_processor_unavailable'
            ) from error
        return

    await dispatcher.feed_update(bot, update)


def create_telegram_router(
    bot: Bot,
    dispatcher: Dispatcher,
    *,
    processor: TelegramWebhookProcessor | None = None,
) -> APIRouter:
    router = APIRouter()
    webhook_path = settings.get_telegram_webhook_path()
    secret_token = settings.WEBHOOK_SECRET_TOKEN

    @router.post(webhook_path)
    async def telegram_webhook(request: Request) -> JSONResponse:
        # Без секрета любой мог бы прислать апдейт от имени любого user_id (в том
        # числе админа) — как и платёжные вебхуки, без секрета не принимаем.
        if not secret_token:
            logger.error('Telegram webhook отклонён: WEBHOOK_SECRET_TOKEN не задан')
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='webhook_secret_not_configured')
        header_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token') or ''
        if not hmac.compare_digest(header_token.encode(), secret_token.encode()):
            logger.warning('Получен Telegram webhook с неверным секретом')
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_secret_token')

        content_type = request.headers.get('content-type', '')
        if content_type and 'application/json' not in content_type.lower():
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail='invalid_content_type')

        try:
            payload: Any = await request.json()
        except Exception as error:  # pragma: no cover - defensive logging
            logger.error('Ошибка чтения Telegram webhook', error=error)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_payload') from error

        try:
            update = Update.model_validate(payload)
        except Exception as error:  # pragma: no cover - defensive logging
            logger.error('Ошибка валидации Telegram update', error=error)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid_update') from error

        await _dispatch_update(update, dispatcher=dispatcher, bot=bot, processor=processor)
        return JSONResponse({'status': 'ok'})

    @router.get('/health/telegram-webhook')
    async def telegram_webhook_health() -> JSONResponse:
        return JSONResponse(
            {
                'status': 'ok',
                'mode': settings.get_bot_run_mode(),
                'path': webhook_path,
                'webhook_configured': bool(settings.get_telegram_webhook_url()),
                'queue_maxsize': settings.get_webhook_queue_maxsize(),
                'workers': settings.get_webhook_worker_count(),
            }
        )

    return router
