"""«Проверить статус» отвечает словами, а не словом провайдера.

Platega — 796 из 858 нажатий «Проверить статус» за 30 дней. Неоплаченный платёж давал
«Текущий статус платежа: PENDING» или «…: CANCELED»: человек не понимал, ждать ему или платить заново.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.handlers.balance.pay2328 as pay2328_handlers
import app.handlers.balance.platega as platega_handlers


USER = SimpleNamespace(id=1, language='ru')
NOT_RECEIVED = 'Платёж ещё не поступил. Если вы оплатили — подождите минуту и проверьте снова.'
FAILED = 'Платёж не прошёл, деньги не списаны.'
# Слово провайдера: латиница подряд (PENDING, CANCELED, something_new).
PROVIDER_WORD = re.compile(r'[A-Za-z_]{4,}')


def _callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.bot = MagicMock()
    return callback


async def _platega_answer(status: str, *, is_paid: bool = False) -> str:
    payment = SimpleNamespace(id=5, user_id=USER.id, status=status, is_paid=is_paid, user=USER)
    service = MagicMock()
    service.get_platega_payment_status = AsyncMock(
        return_value={'payment': payment, 'status': status, 'is_paid': is_paid, 'remote': None}
    )
    callback = _callback('check_platega_5')

    with (
        patch('app.database.crud.platega.get_platega_payment_by_id', AsyncMock(return_value=payment)),
        patch.object(platega_handlers, 'PaymentService', return_value=service),
    ):
        await platega_handlers.check_platega_payment_status(callback, db_user=USER, db=AsyncMock())

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get('show_alert') is True
    return callback.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['PENDING', 'INPROGRESS', 'pending', 'SOMETHING_NEW', ''])
async def test_platega_unpaid_payment_is_explained_in_words(status: str) -> None:
    answer = await _platega_answer(status)

    assert answer == NOT_RECEIVED
    assert not PROVIDER_WORD.search(answer)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['CANCELED', 'CANCELLED', 'FAILED', 'EXPIRED'])
async def test_platega_failed_payment_says_money_was_not_charged(status: str) -> None:
    answer = await _platega_answer(status)

    assert answer == FAILED
    assert not PROVIDER_WORD.search(answer)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['CONFIRMED', 'CHARGEBACKED'])
async def test_platega_paid_payment_keeps_its_answer(status: str) -> None:
    answer = await _platega_answer(status, is_paid=True)

    assert 'Платёж уже зачислен' in answer
    assert status not in answer


@pytest.mark.asyncio
async def test_pay2328_unknown_status_is_not_shown_raw() -> None:
    payment = SimpleNamespace(id=5, user_id=USER.id, status='something_new', is_paid=False, user=USER)
    service = MagicMock()
    service.sync_pay2328_payment_status = AsyncMock(return_value=payment)
    callback = _callback('check_pay2328_5')

    with (
        patch('app.database.crud.pay2328.get_pay2328_payment_by_id', AsyncMock(return_value=payment)),
        patch.object(pay2328_handlers, 'PaymentService', return_value=service),
    ):
        await pay2328_handlers.check_pay2328_payment_status(callback, db_user=USER, db=AsyncMock())

    answer = callback.answer.await_args.args[0]
    assert answer == NOT_RECEIVED
    assert 'something_new' not in answer
