"""Кнопка «Проверить статус» показывает только свои платежи.

Локальный id платежа приходит в callback_data, а её клиент может подменить
(MTProto getBotCallbackAnswer). Раньше обработчики check_* грузили платёж по id
без проверки владельца: перебором открывались суммы и статусы чужих платежей,
токен СБП и ссылки на оплату, а бот дёргал API провайдера по чужим счетам.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.handlers.balance.cryptobot as cryptobot_handlers
import app.handlers.balance.main as balance_main
import app.handlers.balance.platega as platega_handlers
from app.handlers import simple_subscription


OWNER_ID = 1
ATTACKER = SimpleNamespace(id=2, language='ru')


def _callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.bot = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    return callback


def _foreign_payment() -> SimpleNamespace:
    return SimpleNamespace(id=5, user_id=OWNER_ID, status='pending', metadata_json='{"confirmation_token": "ct"}')


def _assert_not_found_alert(callback: MagicMock) -> None:
    callback.answer.assert_awaited_once()
    assert 'не найден' in callback.answer.await_args.args[0]
    assert callback.answer.await_args.kwargs.get('show_alert') is True


@pytest.mark.asyncio
async def test_platega_foreign_payment_is_not_checked_with_provider() -> None:
    callback = _callback('check_platega_5')
    payment_service_cls = MagicMock()

    with (
        patch('app.database.crud.platega.get_platega_payment_by_id', AsyncMock(return_value=_foreign_payment())),
        patch.object(platega_handlers, 'PaymentService', payment_service_cls),
    ):
        await platega_handlers.check_platega_payment_status(callback, db_user=ATTACKER, db=AsyncMock())

    _assert_not_found_alert(callback)
    payment_service_cls.assert_not_called()


@pytest.mark.asyncio
async def test_platega_own_payment_still_checked() -> None:
    callback = _callback('check_platega_5')
    service = MagicMock()
    service.get_platega_payment_status = AsyncMock(return_value=None)

    with (
        patch('app.database.crud.platega.get_platega_payment_by_id', AsyncMock(return_value=_foreign_payment())),
        patch.object(platega_handlers, 'PaymentService', return_value=service),
    ):
        await platega_handlers.check_platega_payment_status(
            callback, db_user=SimpleNamespace(id=OWNER_ID, language='ru'), db=AsyncMock()
        )

    service.get_platega_payment_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_cryptobot_foreign_payment_hidden() -> None:
    callback = _callback('check_cryptobot_5')

    with patch('app.database.crud.cryptobot.get_cryptobot_payment_by_id', AsyncMock(return_value=_foreign_payment())):
        await cryptobot_handlers.check_cryptobot_payment_status(callback, db_user=ATTACKER, db=AsyncMock())

    _assert_not_found_alert(callback)
    callback.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_sbp_confirmation_token_not_sent_to_foreign_user() -> None:
    callback = _callback('sbp_pay_5')

    with patch(
        'app.database.crud.yookassa.get_yookassa_payment_by_local_id', AsyncMock(return_value=_foreign_payment())
    ):
        await balance_main.handle_sbp_payment(callback, db_user=ATTACKER, db=AsyncMock())

    _assert_not_found_alert(callback)
    callback.message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_simple_wata_foreign_payment_is_not_checked_with_provider() -> None:
    callback = _callback('check_simple_wata_5')
    payment_service_cls = MagicMock()

    with (
        patch('app.database.crud.wata.get_wata_payment_by_id', AsyncMock(return_value=_foreign_payment())),
        patch.object(simple_subscription, 'PaymentService', payment_service_cls),
    ):
        await simple_subscription.check_simple_wata_payment_status(callback, db_user=ATTACKER, db=AsyncMock())

    _assert_not_found_alert(callback)
    payment_service_cls.assert_not_called()
