"""Конфиг приложений кэшируется, но каждый запрос получает свою копию."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cabinet.routes.subscription_modules import status


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    status._app_config_cache.clear()
    monkeypatch.setattr(status, '_get_remnawave_config_uuid', lambda: 'uuid')
    client = AsyncMock()
    client.get_subscription_page_config = AsyncMock(
        return_value=SimpleNamespace(config={'platforms': {'ios': [{'name': 'Happ'}]}})
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(status, 'RemnaWaveService', lambda: SimpleNamespace(get_api_client=lambda: context))
    yield client
    status._app_config_cache.clear()


async def test_second_request_does_not_call_panel(api: AsyncMock) -> None:
    await status._load_app_config_async()
    await status._load_app_config_async()

    assert api.get_subscription_page_config.await_count == 1


async def test_user_link_does_not_leak_to_next_request(api: AsyncMock) -> None:
    first = await status._load_app_config_async()
    first['platforms']['ios'][0]['deepLink'] = 'happ://secret-of-user-1'

    second = await status._load_app_config_async()

    assert 'deepLink' not in second['platforms']['ios'][0]


async def test_stale_config_is_served_when_panel_fails(api: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    await status._load_app_config_async()
    monkeypatch.setattr(status, '_APP_CONFIG_TTL_SECONDS', 0)
    api.get_subscription_page_config = AsyncMock(side_effect=RuntimeError('panel down'))

    assert (await status._load_app_config_async())['platforms']
