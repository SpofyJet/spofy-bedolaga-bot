"""A rejected automatic top-up must explain how to continue without creating an invoice."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers.balance import main as balance_main, wata
from app.states import BalanceStates


@pytest.fixture
def payment_environment(monkeypatch):
    settings = SimpleNamespace(
        WATA_MIN_AMOUNT_KOPEKS=5000,
        WATA_MAX_AMOUNT_KOPEKS=10000,
        is_wata_enabled=lambda: True,
        get_balance_payment_description=lambda *_args, **_kwargs: 'Balance top-up',
        format_price=lambda amount: f'{amount / 100:.2f} ₽',
        get_support_contact_display_html=lambda: 'support',
    )
    monkeypatch.setattr(balance_main, 'settings', settings)
    monkeypatch.setattr(wata, 'settings', settings)

    invoice = {'payment_url': 'https://example.com/payment', 'local_payment_id': 42}
    service = SimpleNamespace(create_wata_payment=AsyncMock(return_value=invoice))
    factory = MagicMock(return_value=service)
    monkeypatch.setattr(wata, 'PaymentService', factory)
    return SimpleNamespace(settings=settings, service=service, factory=factory)


@pytest.fixture
def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=7, user_id=7))


@pytest.fixture
def user():
    return SimpleNamespace(id=7, telegram_id=7, username='test_user', language='ru', restriction_topup=False)


def _message(text=None):
    message = MagicMock(spec=types.Message)
    message.text = text
    message.message_id = 10
    message.chat = SimpleNamespace(id=7)
    invoice_message = SimpleNamespace(chat=message.chat, message_id=11)
    message.answer = AsyncMock(return_value=invoice_message)
    message.answer_photo = AsyncMock(return_value=invoice_message)
    message.delete = AsyncMock()
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize('typed', ['nan', 'NaN', 'sNaN', 'inf', '-Infinity', 'not-a-number'])
async def test_nonfinite_amount_never_reaches_payment_provider(state, user, monkeypatch, typed):
    route = AsyncMock()
    monkeypatch.setattr(balance_main, 'route_payment_by_method', route)
    await state.set_state(BalanceStates.waiting_for_amount)
    await state.set_data({'payment_method': 'wata'})
    message = _message(typed)

    await balance_main.process_topup_amount(message, user, state)

    route.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert await state.get_state() == BalanceStates.waiting_for_amount.state


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['wata'])
async def test_rejected_purchase_topup_keeps_input_open_until_user_retries(payment_environment, state, user, method):
    # A 100-ruble purchase with a 60-ruble balance prefills the missing 40 rubles.
    cart = {'tariff_id': 1, 'period_days': 30, 'total_price': 10000}
    await state.set_state('SubscriptionStates:cart_saved_for_topup')
    await state.set_data({'saved_cart': cart, 'total_price': 10000})
    message = _message()
    callback = SimpleNamespace(data=f'topup_amount|{method}|4000', message=message, answer=AsyncMock())

    await balance_main.handle_topup_amount_callback(callback, user, state)

    hint = message.answer.await_args.args[0]
    assert 'отправьте боту сообщение' in hint
    assert 'не меньше 50 ₽' in hint
    assert 'Например, отправьте: 50' in hint
    callback.answer.assert_awaited_once()
    payment_environment.factory.assert_not_called()
    assert await state.get_state() == BalanceStates.waiting_for_amount.state
    assert await state.get_data() == {'saved_cart': cart, 'total_price': 10000, 'payment_method': method}

    # Retrying with too much must still leave an actionable prompt and no invoice.
    too_large = _message('101')
    await balance_main.process_topup_amount(too_large, user, state)
    maximum_hint = too_large.answer.await_args.args[0]
    assert 'отправьте боту сообщение' in maximum_hint
    assert 'не больше 100 ₽' in maximum_hint
    payment_environment.factory.assert_not_called()
    assert await state.get_state() == BalanceStates.waiting_for_amount.state
    assert (await state.get_data())['saved_cart'] == cart

    retry = _message('50')
    await balance_main.process_topup_amount(retry, user, state)

    expected = payment_environment.service.create_wata_payment
    expected.assert_awaited_once()
    assert expected.await_args.kwargs['amount_kopeks'] == 5000


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['manual', 'direct'])
@pytest.mark.parametrize(
    ('minimum', 'maximum', 'displayed_minimum', 'example'),
    [
        pytest.param(5055, 10000, '50.55', '51', id='fractional-minimum'),
        pytest.param(4999999, 5000000, '49999.99', '50000', id='manual-input-ceiling'),
        pytest.param(5055, 5099, '50.55', None, id='no-valid-whole-ruble-example'),
        pytest.param(5000001, 6000000, '50000.01', None, id='minimum-exceeds-manual-input-ceiling'),
    ],
)
async def test_minimum_hint_only_suggests_an_accepted_whole_ruble_amount(
    payment_environment, state, user, entry, minimum, maximum, displayed_minimum, example
):
    payment_environment.settings.WATA_MIN_AMOUNT_KOPEKS = minimum
    payment_environment.settings.WATA_MAX_AMOUNT_KOPEKS = maximum
    await state.set_state(BalanceStates.waiting_for_amount)
    await state.set_data({'payment_method': 'wata'})
    message = _message('40')

    if entry == 'manual':
        await balance_main.process_topup_amount(message, user, state)
    else:
        await wata.process_wata_payment_amount(message, user, AsyncMock(), 4000, state)

    hint = message.answer.await_args.args[0]
    if minimum > 5000000:
        assert 'Выберите другой способ оплаты' in hint
        assert displayed_minimum in hint
        assert 'отправьте боту сообщение' not in hint
    else:
        assert 'отправьте боту сообщение' in hint
        assert f'не меньше {displayed_minimum} ₽' in hint
    if example is None:
        assert 'Например' not in hint
    else:
        assert hint.split('Например, отправьте: ')[1] == example
    payment_environment.factory.assert_not_called()
    assert await state.get_state() == BalanceStates.waiting_for_amount.state


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['wata'])
@pytest.mark.parametrize('typed', ['64.07', '64,07', '64.10', '64.21'])
async def test_retry_at_exact_fractional_minimum_does_not_lose_a_kopeck(
    payment_environment, state, user, method, typed
):
    expected_kopeks = {'64.07': 6407, '64,07': 6407, '64.10': 6410, '64.21': 6421}[typed]
    payment_environment.settings.WATA_MIN_AMOUNT_KOPEKS = expected_kopeks
    await state.set_state(BalanceStates.waiting_for_amount)
    await state.set_data({'payment_method': method, 'saved_cart': {'total_price': 10000}})

    await balance_main.process_topup_amount(_message(typed), user, state)

    expected = payment_environment.service.create_wata_payment
    expected.assert_awaited_once()
    assert expected.await_args.kwargs['amount_kopeks'] == expected_kopeks


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['platega', 'heleket_card', 'wata_sbp', 'cryptobot'])
async def test_manual_amount_reaches_other_payment_routes_without_float_truncation(state, user, monkeypatch, method):
    route = AsyncMock(return_value=True)
    monkeypatch.setattr(balance_main, 'route_payment_by_method', route)
    await state.set_state(BalanceStates.waiting_for_amount)
    await state.set_data({'payment_method': method, 'saved_cart': {'total_price': 10000}})
    message = _message('64.07')

    await balance_main.process_topup_amount(message, user, state)

    route.assert_awaited_once_with(message, user, 6407, state, method)
    assert (await state.get_data())['saved_cart'] == {'total_price': 10000}
