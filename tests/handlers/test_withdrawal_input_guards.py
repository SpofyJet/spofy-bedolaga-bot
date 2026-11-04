"""Вывод реферального баланса и промокод: фото/стикер и «inf» не роняют хендлер.

`message.text.strip()` падал на фото и стикерах (text = None), а «inf»
доходил до int() и давал OverflowError — без @error_handler состояние висело.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.handlers import promocode, referral
from app.states import ReferralWithdrawalStates


def _message(text):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=1), answer=AsyncMock())


def _state(data):
    return SimpleNamespace(get_data=AsyncMock(return_value=data), update_data=AsyncMock(), set_state=AsyncMock())


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('1500', 150000),
        ('1 500,50 ₽', 150050),
        ('99.999', 9999),
        ('-5', -500),
        ('inf', None),
        ('-Infinity', None),
        ('nan', None),
        ('1e999999999', None),
        ('9999999999', 999999999900),
        ('1e10', None),
        ('0', 0),
        ('сто рублей', None),
        ('', None),
        (None, None),
    ],
)
def test_parse_withdrawal_amount(raw, expected):
    assert referral.parse_withdrawal_amount_kopeks(raw) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [None, 'inf', 'nan', '1e999999999', 'abc'])
async def test_bad_amount_reprompts_and_keeps_state(text):
    message = _message(text)
    state = _state({'available_balance': 100_000})

    await referral.process_withdrawal_amount(message, SimpleNamespace(language='ru'), AsyncMock(), state)

    message.answer.assert_awaited_once()
    assert 'распознать сумму' in message.answer.await_args.args[0]
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_amount_moves_to_details(monkeypatch):
    message = _message('600')
    state = _state({'available_balance': 100_000})
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_MIN_AMOUNT_KOPEKS', 50_000)

    await referral.process_withdrawal_amount(message, SimpleNamespace(language='ru'), AsyncMock(), state)

    state.update_data.assert_awaited_once_with(withdrawal_amount=60_000)
    state.set_state.assert_awaited_once_with(ReferralWithdrawalStates.waiting_for_payment_details)


@pytest.mark.asyncio
async def test_photo_instead_of_details_reprompts():
    message = _message(None)
    state = _state({'withdrawal_amount': 60_000})

    await referral.process_payment_details(message, SimpleNamespace(language='ru'), AsyncMock(), state)

    assert 'текстом' in message.answer.await_args.args[0]
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_sticker_instead_of_promocode_reprompts():
    message = _message(None)
    state = SimpleNamespace(get_data=AsyncMock(return_value={}), clear=AsyncMock())

    await promocode.process_promocode(message, SimpleNamespace(language='ru'), state, AsyncMock())

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == promocode.get_texts('ru').t('PROMOCODE_EMPTY_INPUT', '')
