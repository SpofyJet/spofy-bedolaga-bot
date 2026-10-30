"""Тесты для MenuLayoutService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import InlineKeyboardButton

from app.config import settings
from app.services.menu_layout.context import MenuContext
from app.services.menu_layout.service import MenuLayoutService


@pytest.mark.anyio
async def test_build_button_connect_direct_mode_with_url():
    """Тест: кнопка connect с open_mode=direct и валидным URL должна создавать WebAppInfo."""
    button_config = {
        'type': 'builtin',
        'builtin_id': 'connect',
        'text': {'ru': '🔗 Подключиться'},
        'action': 'subscription_connect',
        'open_mode': 'direct',
        'webapp_url': 'https://example.com/miniapp',
    }

    context = MenuContext(
        language='ru',
        has_active_subscription=True,
        subscription_is_active=True,
    )

    texts = MagicMock()
    texts.t = lambda key, default: default

    button = MenuLayoutService._build_button(button_config, context, texts)

    assert button is not None
    assert isinstance(button, InlineKeyboardButton)
    assert button.web_app is not None
    assert button.web_app.url == 'https://example.com/miniapp'
    assert button.callback_data is None


@pytest.mark.anyio
async def test_build_button_connect_direct_mode_with_subscription_url():
    """Тест: кнопка connect с open_mode=direct должна получать URL из подписки."""
    button_config = {
        'type': 'builtin',
        'builtin_id': 'connect',
        'text': {'ru': '🔗 Подключиться'},
        'action': 'subscription_connect',
        'open_mode': 'direct',
        'webapp_url': None,
    }

    # Мокаем подписку с URL
    mock_subscription = MagicMock()
    mock_subscription.subscription_url = 'https://subscription.example.com/link'
    mock_subscription.subscription_crypto_link = None

    context = MenuContext(
        language='ru',
        has_active_subscription=True,
        subscription_is_active=True,
        subscription=mock_subscription,
    )

    texts = MagicMock()
    texts.t = lambda key, default: default

    with patch('app.utils.subscription_utils.get_display_subscription_link') as mock_get_link:
        mock_get_link.return_value = 'https://subscription.example.com/link'

        button = MenuLayoutService._build_button(button_config, context, texts)

        assert button is not None
        assert isinstance(button, InlineKeyboardButton)
        assert button.web_app is not None
        assert button.web_app.url == 'https://subscription.example.com/link'


@pytest.mark.anyio
async def test_build_button_connect_callback_mode():
    """Тест: кнопка connect с open_mode=callback должна создавать callback кнопку."""
    button_config = {
        'type': 'builtin',
        'builtin_id': 'connect',
        'text': {'ru': '🔗 Подключиться'},
        'action': 'subscription_connect',
        'open_mode': 'callback',
        'webapp_url': None,
    }

    context = MenuContext(
        language='ru',
        has_active_subscription=True,
        subscription_is_active=True,
    )

    texts = MagicMock()
    texts.t = lambda key, default: default

    button = MenuLayoutService._build_button(button_config, context, texts)

    assert button is not None
    assert isinstance(button, InlineKeyboardButton)
    assert button.callback_data == 'subscription_connect'
    assert button.web_app is None


@pytest.mark.anyio
async def test_build_button_connect_direct_mode_fallback_to_callback():
    """Тест: кнопка connect с open_mode=direct без URL должна fallback на callback."""
    button_config = {
        'type': 'builtin',
        'builtin_id': 'connect',
        'text': {'ru': '🔗 Подключиться'},
        'action': 'subscription_connect',
        'open_mode': 'direct',
        'webapp_url': None,
    }

    context = MenuContext(
        language='ru',
        has_active_subscription=True,
        subscription_is_active=True,
        subscription=None,  # Нет подписки
    )

    texts = MagicMock()
    texts.t = lambda key, default: default

    with patch('app.services.menu_layout.service.settings') as mock_settings:
        mock_settings.MINIAPP_CUSTOM_URL = None

        button = MenuLayoutService._build_button(button_config, context, texts)

        assert button is not None
        assert isinstance(button, InlineKeyboardButton)
        # Должен fallback на callback_data, так как URL не найден
        assert button.callback_data == 'subscription_connect'


@pytest.mark.anyio
async def test_saved_connect_layout_allows_inactive_subscription_with_exact_link():
    """Старые active-only конфиги не должны скрывать существующую саб-ссылку."""
    subscription = MagicMock(
        id=42,
        subscription_url='https://example.invalid/sub/42',
        subscription_crypto_link=None,
    )
    context = MenuContext(
        has_active_subscription=False,
        subscription_is_active=False,
        subscription=subscription,
    )
    config = MenuLayoutService.get_default_config()

    with (
        patch.object(MenuLayoutService, 'get_config', new=AsyncMock(return_value=config)),
        patch.object(type(settings), 'is_multi_tariff_enabled', return_value=True),
    ):
        keyboard = await MenuLayoutService.build_keyboard(MagicMock(), context)

    connect_buttons = [button for row in keyboard.inline_keyboard for button in row if button.text == '🔗 Подключиться']
    assert len(connect_buttons) == 1
    assert connect_buttons[0].callback_data == 'sl:42'


@pytest.mark.anyio
async def test_saved_connect_layout_hides_inactive_subscription_without_link():
    subscription = MagicMock(
        id=42,
        subscription_url=None,
        subscription_crypto_link=None,
    )
    context = MenuContext(
        has_active_subscription=False,
        subscription_is_active=False,
        subscription=subscription,
    )
    config = MenuLayoutService.get_default_config()

    with patch.object(MenuLayoutService, 'get_config', new=AsyncMock(return_value=config)):
        keyboard = await MenuLayoutService.build_keyboard(MagicMock(), context)

    assert all(button.text != '🔗 Подключиться' for row in keyboard.inline_keyboard for button in row)
