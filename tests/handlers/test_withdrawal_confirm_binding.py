"""«✅ Подтвердить» вывода привязано к текущему шагу и гаснет после использования.

Раньше состояние очищалось до создания заявки, а кнопка оставалась: после
ошибки повторное нажатие отправляло пустую сумму и давало «Некорректная сумма».
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers import referral
from app.states import ReferralWithdrawalStates


CONFIRMING = ReferralWithdrawalStates.confirming.state


def _state(state_value, data):
    return SimpleNamespace(
        get_state=AsyncMock(return_value=state_value),
        get_data=AsyncMock(return_value=data),
        update_data=AsyncMock(),
        set_state=AsyncMock(),
        clear=AsyncMock(),
    )


def _callback(data):
    return SimpleNamespace(
        data=data, answer=AsyncMock(), message=SimpleNamespace(edit_reply_markup=AsyncMock()), bot=MagicMock()
    )


def _user():
    return SimpleNamespace(id=1, telegram_id=1, email=None, full_name='Тест', language='ru')


@pytest.mark.asyncio
async def test_details_screen_puts_nonce_into_confirm_button():
    message = SimpleNamespace(text='СБП +7 999 123-45-67 Сбербанк', answer=AsyncMock())
    state = _state(ReferralWithdrawalStates.waiting_for_payment_details.state, {'withdrawal_amount': 60_000})

    await referral.process_payment_details(message, _user(), AsyncMock(), state)

    nonce = state.update_data.await_args.kwargs['confirm_nonce']
    markup = message.answer.await_args.kwargs['reply_markup']
    assert markup.inline_keyboard[0][0].callback_data == f'referral_withdrawal_confirm_{nonce}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('state_value', 'data', 'callback_data'),
    [
        # после ошибки/успеха состояние очищено — второе нажатие
        (None, {}, 'referral_withdrawal_confirm_abcd1234'),
        # кнопка со старого экрана, а человек уже оформил заявку заново
        (
            CONFIRMING,
            {'withdrawal_amount': 60_000, 'confirm_nonce': 'new00000'},
            'referral_withdrawal_confirm_old00000',
        ),
    ],
)
async def test_stale_confirm_does_not_create_request(monkeypatch, state_value, data, callback_data):
    create = AsyncMock()
    monkeypatch.setattr(referral.referral_withdrawal_service, 'create_withdrawal_request', create)
    callback = _callback(callback_data)

    await referral.confirm_withdrawal_request(callback, _user(), AsyncMock(), _state(state_value, data))

    create.assert_not_awaited()
    assert 'устарела' in callback.answer.await_args.args[0]
    markup = callback.message.edit_reply_markup.await_args.kwargs['reply_markup']
    assert [b.callback_data for row in markup.inline_keyboard for b in row] == ['referral_withdrawal']


@pytest.mark.asyncio
async def test_error_retires_confirm_button(monkeypatch):
    create = AsyncMock(return_value=(None, 'Недостаточно средств'))
    monkeypatch.setattr(referral.referral_withdrawal_service, 'create_withdrawal_request', create)
    callback = _callback('referral_withdrawal_confirm_abcd1234')
    state = _state(CONFIRMING, {'withdrawal_amount': 60_000, 'payment_details': 'x' * 12, 'confirm_nonce': 'abcd1234'})

    await referral.confirm_withdrawal_request(callback, _user(), AsyncMock(), state)

    create.assert_awaited_once()
    state.clear.assert_awaited_once()
    assert 'Недостаточно средств' in callback.answer.await_args.args[0]
    callback.message.edit_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_button_without_nonce_still_works(monkeypatch):
    create = AsyncMock(return_value=(None, 'stop here'))
    monkeypatch.setattr(referral.referral_withdrawal_service, 'create_withdrawal_request', create)
    state = _state(CONFIRMING, {'withdrawal_amount': 60_000, 'payment_details': 'x' * 12})

    await referral.confirm_withdrawal_request(_callback('referral_withdrawal_confirm'), _user(), AsyncMock(), state)

    create.assert_awaited_once()
    assert create.await_args.args[1:] == (1, 60_000, 'x' * 12)
