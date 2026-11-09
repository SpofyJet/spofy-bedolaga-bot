"""Глобальные фикстуры и настройки окружения для тестов."""

import asyncio
import inspect
import os
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest


# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Тесты не должны видеть боевое окружение. ``Settings`` читает ``.env`` из корня
# проекта, а переменные процесса имеют приоритет над ``.env``; агенты-помощники
# (Kimi, Claude Code) и ``docker exec`` к тому же экспортируют боевой ``.env`` в
# окружение. Один раз это уже закончилось тем, что фикстуры pytest ушли в
# админ-чат как «покупки» (30.10.2026). Поэтому здесь не ``setdefault``, а
# жёсткая подмена всего, через что тест может дотянуться до боя: токен бота,
# админ-уведомления, база, ключ панели. Для настоящего PostgreSQL есть
# отдельная ``TEST_DATABASE_URL`` (tests/fixtures/postgres_db.py), для панели —
# ``TEST_REMNAWAVE_URL``/``TEST_REMNAWAVE_TOKEN_FILE``.
_ISOLATED_ENV = {
    'DATABASE_MODE': 'postgresql',
    'DATABASE_URL': 'postgresql+asyncpg://user:pass@localhost/test_db',
    'BOT_TOKEN': 'test-token',
    'ADMIN_NOTIFICATIONS_ENABLED': 'false',
    'ADMIN_REPORTS_ENABLED': 'false',
    'REMNAWAVE_API_URL': '',
    'REMNAWAVE_API_KEY': '',
}
os.environ.update(_ISOLATED_ENV)

# Module-level singleton `backup_service = BackupService()` в backup_service.py
# при импорте делает `Path(settings.BACKUP_LOCATION).mkdir(parents=True)`.
# Дефолт `/app/data/backups` — это путь docker-контейнера, недоступный на dev.
# Подменяем на temp-директорию ещё до первого импорта приложения, чтобы тест-
# коллекция не падала с `OSError: Read-only file system: '/app'`.
import tempfile as _tempfile


os.environ.setdefault('BACKUP_LOCATION', _tempfile.mkdtemp(prefix='bedolaga_test_backups_'))

# Создаём заглушки для драйверов, которых может не быть в окружении тестов.
sys.modules.setdefault('asyncpg', types.ModuleType('asyncpg'))
sys.modules.setdefault('aiosqlite', types.ModuleType('aiosqlite'))

# Эмуляция redis.asyncio, чтобы модуль кеша мог импортироваться.
if 'redis.asyncio' not in sys.modules:
    redis_module = types.ModuleType('redis')
    redis_async_module = types.ModuleType('redis.asyncio')
    redis_exceptions_module = types.ModuleType('redis.exceptions')

    class _FakeRedisError(Exception):
        """Base Redis exception for tests."""

    class _FakeNoScriptError(_FakeRedisError):
        """Redis script cache miss exception for tests."""

    class _FakeRedisClient:
        async def ping(self):
            """Имитируем успешный ответ ping."""
            return True

        async def close(self):
            """Закрытие соединения ничего не делает."""

        async def get(self, key):
            return None

        async def set(self, key, value, ex=None):
            return True

        async def delete(self, *keys):
            return 0

        async def keys(self, pattern='*'):
            return []

        async def exists(self, key):
            return False

        async def expire(self, key, seconds):
            return True

        async def incr(self, key):
            return 1

    def _from_url(url, **kwargs):
        return _FakeRedisClient()

    # Политика повторов подключения: код создания клиента импортирует её жёстко,
    # чтобы смена пути в библиотеке была видна сразу, а не молча отключала повторы.
    redis_retry_module = types.ModuleType('redis.asyncio.retry')
    redis_backoff_module = types.ModuleType('redis.backoff')

    class _FakeRetry:
        def __init__(self, backoff, retries, supported_errors=()):
            self._backoff = backoff
            self._retries = retries
            self._supported_errors = supported_errors

    class _FakeBackoff:
        def __init__(self, base=0.008, cap=0.512):
            self.base = base
            self.cap = cap

    redis_retry_module.Retry = _FakeRetry
    redis_backoff_module.ExponentialWithJitterBackoff = _FakeBackoff

    redis_module.__path__ = []
    redis_async_module.__path__ = []
    redis_module.asyncio = redis_async_module
    redis_module.backoff = redis_backoff_module
    redis_async_module.retry = redis_retry_module
    redis_async_module.from_url = _from_url
    redis_async_module.Redis = _FakeRedisClient
    redis_exceptions_module.RedisError = _FakeRedisError
    redis_exceptions_module.NoScriptError = _FakeNoScriptError
    sys.modules['redis'] = redis_module
    sys.modules['redis.asyncio'] = redis_async_module
    sys.modules['redis.asyncio.retry'] = redis_retry_module
    sys.modules['redis.backoff'] = redis_backoff_module
    sys.modules['redis.exceptions'] = redis_exceptions_module


# ── Страховка от выхода в Telegram ───────────────────────────────────────────
# Даже если тест включит ADMIN_NOTIFICATIONS_ENABLED и соберёт бота через
# create_bot(), запрос к api.telegram.org не уйдёт: сетевой слой aiogram
# подменён на исключение. Сервисы-уведомители работают best-effort и глотают
# исключения, так что тесты это не ломает, а текст в логе объясняет причину.
class TelegramApiBlockedInTests(RuntimeError):
    """Тест попытался отправить настоящий запрос в Telegram Bot API."""


try:
    from aiogram.client.session.aiohttp import AiohttpSession as _AiohttpSession
except Exception:  # pragma: no cover - окружение без aiogram
    _AiohttpSession = None

if _AiohttpSession is not None:
    _real_make_request = _AiohttpSession.make_request
    _LOOPBACK_MARKERS = ('://127.0.0.1', '://localhost', '://[::1]')

    async def _guarded_make_request(self, bot, method, timeout=None):
        # Локальный заглушечный сервер (tests/utils/test_rich_media.py) — можно.
        api_base = str(getattr(getattr(self, 'api', None), 'base', ''))
        if any(marker in api_base for marker in _LOOPBACK_MARKERS):
            return await _real_make_request(self, bot, method, timeout)
        raise TelegramApiBlockedInTests(
            f'Тесты не ходят в Telegram Bot API (метод {type(method).__name__}): подмените бота на AsyncMock.'
        )

    _AiohttpSession.make_request = _guarded_make_request


@pytest.fixture(autouse=True)
def _block_real_platega(monkeypatch: pytest.MonkeyPatch) -> None:
    """Не пускает тесты в настоящую Platega: после 10 неверных пар она блокирует адрес на час."""
    import aiohttp

    real_request = aiohttp.ClientSession._request

    async def guarded_request(self, method, url, **kwargs):
        if 'platega.io' in str(url):
            raise AssertionError(f'Тест пытался обратиться к настоящей Platega: {method} {url}')
        return await real_request(self, method, url, **kwargs)

    monkeypatch.setattr(aiohttp.ClientSession, '_request', guarded_request)


@pytest.fixture
def fixed_datetime() -> datetime:
    """Возвращает фиксированную отметку времени для воспроизводимых проверок."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope='session')
def registered_paths() -> dict[str, set[str]]:
    """Карта `путь -> {HTTP-методы}` кабинетного роутера, как их реально
    обслуживает приложение.

    Раньше тесты обходили ``router.routes`` и читали ``route.path`` напрямую.
    Начиная со Starlette 1.x вложенные роутеры (``include_router``) хранятся
    лениво как ``_IncludedRouter`` без атрибута ``path``, поэтому такой обход
    ломается. Резолвим фактическую таблицу маршрутов через OpenAPI-схему
    приложения — это устойчиво между версиями Starlette/FastAPI.
    """
    from fastapi import FastAPI

    from app.cabinet.routes import router

    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    return {path: {method.upper() for method in operations} for path, operations in schema.get('paths', {}).items()}


# Auto-load fixture modules so tests don't need explicit imports.
# Promocode/promo-group tests in tests/services/test_promocode_service.py,
# tests/crud/test_promocode_crud.py, and tests/integration/test_promocode_promo_group_flow.py
# all rely on these without importing them directly.
pytest_plugins = [
    'tests.fixtures.promocode_fixtures',
    # Даёт фикстуру postgres_database тестам на настоящем PostgreSQL.
    'tests.fixtures.postgres_db',
]


def _unwrap_test(obj):
    """Возвращает исходную функцию, снимая обёртки pytest и декораторов."""

    unwrapped = obj
    while hasattr(unwrapped, '__wrapped__'):
        unwrapped = unwrapped.__wrapped__
    return unwrapped


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Позволяет запускать async def тесты без дополнительных плагинов."""

    # Пропускаем если pytest-asyncio уже обработал этот тест
    if hasattr(pyfuncitem, '_request') and hasattr(pyfuncitem._request, '_pyfuncitem'):
        markers = list(pyfuncitem.iter_markers())
        for marker in markers:
            if marker.name in ('asyncio', 'anyio'):
                # pytest-asyncio обработает этот тест
                return None

    test_func = _unwrap_test(pyfuncitem.obj)
    if not inspect.iscoroutinefunction(test_func):
        return None

    # Проверяем, не обработан ли уже тест плагином pytest-asyncio
    # Если pyfuncitem.obj не возвращает корутину - пропускаем
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        signature = inspect.signature(test_func)
        call_kwargs = {name: value for name, value in pyfuncitem.funcargs.items() if name in signature.parameters}
        coro = pyfuncitem.obj(**call_kwargs)
        if coro is None:
            # Уже обработано другим плагином
            return None
        loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    return True
