"""Пул соединений в наплыв: запрос не держит своё соединение, пока ждёт второе."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cabinet import dependencies
from app.cabinet.routes import branding
from app.config import settings
from app.services import channel_subscription_service as channel_module


async def test_request_connection_is_released_before_channel_check(monkeypatch):
    order: list[str] = []
    db = AsyncMock()
    db.commit = AsyncMock(side_effect=lambda: order.append('commit'))
    user = MagicMock(id=1, telegram_id=7, status='active', email=None, email_verified=False, cabinet_last_login=None)

    async def channels(_telegram_id):
        order.append('channels')
        return [{'is_subscribed': True}]

    monkeypatch.setattr(dependencies, 'get_token_payload', MagicMock(return_value={'sub': '1'}))
    monkeypatch.setattr(dependencies, 'get_user_by_id', AsyncMock(return_value=user))
    monkeypatch.setattr(
        dependencies, 'blacklist_service', MagicMock(is_user_blacklisted=AsyncMock(return_value=(False, None)))
    )
    monkeypatch.setattr(dependencies, 'maintenance_service', MagicMock(is_maintenance_active=lambda: False))
    monkeypatch.setattr(dependencies, 'mark_user_seen', MagicMock(return_value=False))
    monkeypatch.setattr(dependencies, 'schedule_cabinet_action_log', MagicMock())
    monkeypatch.setattr(channel_module.channel_subscription_service, 'get_channels_with_status', channels)
    monkeypatch.setattr(settings, 'CHANNEL_IS_REQUIRED_SUB', True, raising=False)
    monkeypatch.setattr(type(settings), 'is_admin', lambda *_a, **_k: False, raising=False)

    request = SimpleNamespace(method='GET', url=SimpleNamespace(path='/x'), headers={}, state=SimpleNamespace())
    await dependencies.get_current_cabinet_user(request, SimpleNamespace(credentials='t'), db)

    assert order[:2] == ['commit', 'channels']


@pytest.fixture
def setting_reads(monkeypatch):
    branding._setting_cache.clear()
    read = AsyncMock(return_value='Spofy')
    monkeypatch.setattr(branding, 'read_setting_value', read)
    yield read
    branding._setting_cache.clear()


async def test_settings_are_read_from_database_once(setting_reads):
    assert await branding.get_setting_value(AsyncMock(), 'NAME') == 'Spofy'
    assert await branding.get_setting_value(AsyncMock(), 'NAME') == 'Spofy'
    setting_reads.assert_awaited_once()


async def test_missing_setting_is_cached_too(setting_reads):
    setting_reads.return_value = None
    assert await branding.get_setting_value(AsyncMock(), 'NAME') is None
    assert await branding.get_setting_value(AsyncMock(), 'NAME') is None
    setting_reads.assert_awaited_once()


async def test_cache_expires(setting_reads, monkeypatch):
    clock = iter([100.0, 100.0 + branding._SETTING_CACHE_TTL_SECONDS + 1])
    monkeypatch.setattr(branding, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    await branding.get_setting_value(AsyncMock(), 'NAME')
    await branding.get_setting_value(AsyncMock(), 'NAME')
    assert setting_reads.await_count == 2


async def test_write_is_visible_at_once(setting_reads):
    await branding.get_setting_value(AsyncMock(), 'NAME')
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    await branding.set_setting_value(db, 'NAME', 'New')
    await branding.get_setting_value(AsyncMock(), 'NAME')
    assert setting_reads.await_count == 2
