import inspect
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.states import BalanceStates


"""Rejected top-ups must explain an enterable range and keep manual retry possible."""

PROVIDERS = [
    'cryptobot',
    'pay2328',
    'platega',
    'wata',
]
ENTRIES = [(name, f'process_{name}_payment_amount') for name in PROVIDERS]


class ProviderSettings:
    def __getattr__(self, name):
        if name.endswith('_MIN_AMOUNT_KOPEKS'):
            return 5055
        if name.endswith('_MAX_AMOUNT_KOPEKS'):
            return 5099
        if name.startswith('is_') and name.endswith('_enabled'):
            return lambda: True
        return getattr(settings, name)


@pytest.mark.asyncio
@pytest.mark.parametrize('language', ['ru', 'en', 'ua', 'fa', 'zh'])
@pytest.mark.parametrize('module_name,entry', ENTRIES, ids=[entry for _, entry in ENTRIES])
@pytest.mark.parametrize('bound', ['low', 'high'])
async def test_rejection_keeps_selection_and_shows_exact_enterable_range(
    monkeypatch, module_name, entry, language, bound
):
    module = import_module(f'app.handlers.balance.{module_name}')
    monkeypatch.setattr(module, 'settings', ProviderSettings())
    factory = MagicMock()
    monkeypatch.setattr(module, 'PaymentService', factory)
    if module_name == 'platega':
        monkeypatch.setattr(module, '_get_active_methods', lambda: [2, 'sbp'])
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(BalanceStates.waiting_for_amount)
    selection = {
        'payment_method': module_name,
        'platega_method': 2,
        'saved_cart': {'total_price': 10000},
    }
    await state.set_data(selection)
    message = MagicMock(spec=types.Message)
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    user = SimpleNamespace(id=1, telegram_id=1, language=language, restriction_topup=False)
    fixed_limits = module_name in {'cryptobot', 'pay2328'}
    amount = (4000 if bound == 'low' else 10000001) if fixed_limits else (4000 if bound == 'low' else 5100)
    message.text = f'{amount // 100}.{amount % 100:02d}'
    values = {
        'message': message,
        'db_user': user,
        'db': AsyncMock(),
        'amount_kopeks': amount,
        'state': state,
        'payment_method': module_name,
    }
    handler = inspect.unwrap(getattr(module, entry))
    await handler(**{name: values[name] for name in inspect.signature(handler).parameters})

    factory.assert_not_called()
    assert await state.get_state() == BalanceStates.waiting_for_amount.state
    assert await state.get_data() == selection
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    minimum, maximum = ('100', '50000') if fixed_limits else ('50.55', '50.99')
    assert minimum in text
    assert maximum in text
    assert 'Например, отправьте: 51' not in text  # No whole-ruble value fits 50.55..50.99.
    keyboard = message.answer.await_args.kwargs['reply_markup']
    assert any(button.callback_data == 'balance_topup' for row in keyboard.inline_keyboard for button in row)


@pytest.mark.asyncio
@pytest.mark.parametrize('language', ['ru', 'en', 'ua', 'fa', 'zh'])
@pytest.mark.parametrize('provider,bound', [('cryptobot', 'low'), ('cryptobot', 'high')])
async def test_currency_rejection_offers_a_ruble_input_range(monkeypatch, language, provider, bound):
    module = import_module(f'app.handlers.balance.{provider}')
    config = ProviderSettings()
    monkeypatch.setattr(module, 'settings', config)
    factory = MagicMock()
    monkeypatch.setattr(module, 'PaymentService', factory)
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(BalanceStates.waiting_for_amount)
    selection = {
        'payment_method': 'cryptobot',
        'current_rate': 250 if bound == 'low' else 1,
        'saved_cart': {'total_price': 10000},
    }
    await state.set_data(selection)
    message = MagicMock(spec=types.Message)
    message.answer = AsyncMock()
    user = SimpleNamespace(id=1, language=language, restriction_topup=False)
    amount = 20000 if bound == 'low' else 150000
    await inspect.unwrap(getattr(module, f'process_{provider}_payment_amount'))(
        message, user, AsyncMock(), amount, state
    )

    factory.assert_not_called()
    assert await state.get_state() == BalanceStates.waiting_for_amount.state
    assert await state.get_data() == selection
    text = message.answer.await_args.args[0]
    assert ('250' if bound == 'low' else '100') in text
    assert ('50000' if bound == 'low' else '1000') in text
    assert any(
        button.callback_data == 'balance_topup'
        for row in message.answer.await_args.kwargs['reply_markup'].inline_keyboard
        for button in row
    )
