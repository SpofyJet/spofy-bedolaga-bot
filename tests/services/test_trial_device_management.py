"""Триал управляет своими устройствами (список, удаление), но докупить места не может."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.handlers.subscription import devices


def _callback():
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    return callback


def _trial():
    return SimpleNamespace(id=5, is_trial=True, remnawave_uuid='u-1', user_id=1)


async def test_trial_user_sees_device_list(monkeypatch):
    monkeypatch.setattr(devices, '_resolve_subscription', AsyncMock(return_value=(_trial(), None)))
    monkeypatch.setattr(devices, '_get_panel_user_id', lambda sub, user: 123)
    show = AsyncMock()
    monkeypatch.setattr(devices, 'show_devices_page', show)

    api = MagicMock()
    api.get_user_devices = AsyncMock(return_value={'total': 1, 'devices': [{'hwid': 'abc', 'platform': 'iOS'}]})

    class Service:
        @asynccontextmanager
        async def get_api_client(self):
            yield api

    monkeypatch.setattr('app.services.remnawave_service.RemnaWaveService', Service)
    callback = _callback()

    await devices.handle_device_management(callback, SimpleNamespace(language='ru', id=1), MagicMock())

    show.assert_awaited_once()  # список показан, а не «только для платных»
    assert not any(call.kwargs.get('show_alert') for call in callback.answer.await_args_list)


async def test_trial_still_cannot_buy_device_slots(monkeypatch):
    monkeypatch.setattr(devices, '_resolve_subscription', AsyncMock(return_value=(_trial(), None)))
    callback = _callback()

    await devices.handle_change_devices(callback, SimpleNamespace(language='ru', id=1), MagicMock())

    assert callback.answer.await_args.kwargs.get('show_alert') is True  # покупка мест по-прежнему платная
