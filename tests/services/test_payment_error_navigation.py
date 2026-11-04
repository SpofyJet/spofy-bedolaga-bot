"""Сообщения о сбое оплаты не тупик: под ними «Назад» и «Поддержка»."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _support_on(monkeypatch):
    monkeypatch.setattr(
        'app.services.support_settings_service.SupportSettingsService.is_support_menu_enabled',
        classmethod(lambda cls: True),
    )


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _message():
    message = MagicMock()
    message.answer = AsyncMock()
    message.chat = SimpleNamespace(id=1)
    message.from_user = SimpleNamespace(id=1001)
    message.bot = MagicMock()
    message.bot.delete_message = AsyncMock()
    message.successful_payment = SimpleNamespace(
        total_amount=50, invoice_payload='balance_1_10000', telegram_payment_charge_id='charge-123456789'
    )
    return message


@pytest.mark.asyncio
async def test_stars_enrollment_error_has_back_and_support(monkeypatch):
    import app.handlers.stars_payments as module

    user = SimpleNamespace(id=1, language='ru')
    monkeypatch.setattr(module, 'get_user_by_telegram_id', AsyncMock(return_value=user))
    monkeypatch.setattr(
        module, 'PaymentService', lambda bot: SimpleNamespace(process_stars_payment=AsyncMock(return_value=False))
    )
    state = SimpleNamespace(get_data=AsyncMock(return_value={}), update_data=AsyncMock())
    message = _message()

    await module.handle_successful_payment(message, db=MagicMock(), state=state)

    markup = message.answer.await_args.kwargs['reply_markup']
    assert _callbacks(markup) == ['menu_balance', 'menu_support']


@pytest.mark.asyncio
async def test_stars_processing_crash_has_back_and_support(monkeypatch):
    import app.handlers.stars_payments as module

    monkeypatch.setattr(module, 'get_user_by_telegram_id', AsyncMock(side_effect=RuntimeError('db down')))
    message = _message()

    await module.handle_successful_payment(message, db=MagicMock(), state=MagicMock())

    markup = message.answer.await_args.kwargs['reply_markup']
    assert _callbacks(markup) == ['menu_balance', 'menu_support']


@pytest.mark.asyncio
async def test_platega_creation_failure_without_alternatives_has_navigation(monkeypatch):
    import app.handlers.balance.platega as module
    from app.config import settings

    monkeypatch.setattr(type(settings), 'is_platega_enabled', lambda self: True)
    monkeypatch.setattr(module, '_get_active_methods', lambda: [2])
    monkeypatch.setattr(settings, 'PLATEGA_MIN_AMOUNT_KOPEKS', 100)
    monkeypatch.setattr(settings, 'PLATEGA_MAX_AMOUNT_KOPEKS', 10_000_000)
    monkeypatch.setattr(
        module,
        'PaymentService',
        lambda bot: SimpleNamespace(create_platega_payment=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr('app.utils.payment_fallback.fallback_methods_keyboard', lambda *a, **kw: None)
    user = SimpleNamespace(id=1, language='ru', telegram_id=1001, restriction_topup=False)
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={'platega_method': 2}), clear=AsyncMock(), set_state=AsyncMock()
    )
    message = _message()

    await module.process_platega_payment_amount(message, user, MagicMock(), 50000, state)

    markup = message.answer.await_args.kwargs['reply_markup']
    assert _callbacks(markup) == ['balance_topup', 'menu_support']
