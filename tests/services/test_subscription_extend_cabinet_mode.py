"""Кнопка «Продлить подписку» в уведомлениях при ``MAIN_MENU_MODE=cabinet``.

Продление всегда строится через ``build_subscription_extend_button``: в
cabinet-режиме кнопка ведёт в кабинет (``subscription_extend`` есть в
``CALLBACK_TO_CABINET_PATH``), вне его остаётся обычным callback'ом.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton

from app.config import settings
from app.utils.miniapp_buttons import (
    build_subscription_extend_button,
)


CABINET_URL = 'https://cabinet.example.com'


@pytest.fixture
def cabinet_mode(monkeypatch: pytest.MonkeyPatch):
    """Полностью настроенный cabinet-режим: и режим меню, и URL кабинета."""
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'cabinet', raising=False)
    monkeypatch.setattr(settings, 'MINIAPP_CUSTOM_URL', CABINET_URL, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# Хелпер
# ---------------------------------------------------------------------------


def test_single_tariff_cabinet_button_opens_cabinet(cabinet_mode) -> None:
    button = build_subscription_extend_button('💎 Продлить подписку')

    assert button.web_app is not None
    assert button.web_app.url == f'{CABINET_URL}/subscription'
    assert button.style == 'success'


def test_bot_mode_keeps_callback_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """Вне cabinet-режима кнопка обязана остаться обычным callback'ом."""
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default', raising=False)
    monkeypatch.setattr(settings, 'MINIAPP_CUSTOM_URL', CABINET_URL, raising=False)

    button = build_subscription_extend_button('💎 Продлить подписку')

    assert button.web_app is None
    assert button.callback_data == 'subscription_extend'


def test_cabinet_mode_without_url_falls_back_to_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cabinet-режим без ``MINIAPP_CUSTOM_URL`` не должен ломать кнопку."""
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'cabinet', raising=False)
    monkeypatch.setattr(settings, 'MINIAPP_CUSTOM_URL', '', raising=False)

    button = build_subscription_extend_button('💎 Продлить подписку')

    assert button.web_app is None
    assert button.callback_data == 'subscription_extend'


# ---------------------------------------------------------------------------
# Места вызова
# ---------------------------------------------------------------------------


async def test_expired_notification_keyboard_opens_cabinet(cabinet_mode) -> None:
    """Сквозная проверка на том самом уведомлении из отчёта пользователя."""
    from app.services.monitoring_service import MonitoringService

    service = MonitoringService.__new__(MonitoringService)
    service._send_message_with_logo = AsyncMock()

    user = SimpleNamespace(telegram_id=1, language='ru', id=7)
    subscription = SimpleNamespace(id=42, tariff=None)

    sent = await service._send_subscription_expired_notification(user, subscription, tariff_name='Базовый')

    assert sent is True
    keyboard = service._send_message_with_logo.await_args.kwargs['reply_markup']
    buttons: list[InlineKeyboardButton] = [b for row in keyboard.inline_keyboard for b in row]

    assert all(b.web_app is not None for b in buttons), (
        'Все кнопки уведомления об истечении в cabinet-режиме должны вести в кабинет: '
        f'{[(b.text, b.callback_data) for b in buttons if b.web_app is None]}'
    )
    assert buttons[0].web_app.url == f'{CABINET_URL}/subscription'
