from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.handlers.subscription import tariff_purchase as tp
from app.utils.subscription_utils import offers_device_choice, resolve_chosen_device_limit


def _tariff(**kw):
    base = dict(
        id=3,
        name='С Обходами',
        is_active=True,
        is_daily=False,
        device_limit=3,
        device_price_kopeks=5900,
        max_device_limit=None,
        period_prices={'30': 31000},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_choice_only_for_first_purchase_trial_or_tariff_change():
    tariff = _tariff()
    assert offers_device_choice(tariff, None)
    assert offers_device_choice(tariff, SimpleNamespace(is_trial=True, tariff_id=3))
    assert offers_device_choice(tariff, SimpleNamespace(is_trial=False, tariff_id=2))
    assert not offers_device_choice(tariff, SimpleNamespace(is_trial=False, tariff_id=3))
    assert not offers_device_choice(_tariff(device_price_kopeks=0), None)
    assert not offers_device_choice(_tariff(is_daily=True), None)


def test_chosen_limit_is_validated(monkeypatch):
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)
    tariff = _tariff(max_device_limit=10)
    assert resolve_chosen_device_limit(tariff, None, 5) == 5
    assert resolve_chosen_device_limit(tariff, None, '7') == 7
    assert resolve_chosen_device_limit(tariff, None, 2) == 3
    assert resolve_chosen_device_limit(tariff, None, 11) == 3
    assert resolve_chosen_device_limit(tariff, None, 'x') == 3
    assert resolve_chosen_device_limit(tariff, None, None) == 3
    assert resolve_chosen_device_limit(_tariff(device_price_kopeks=None), None, 5) == 3


async def test_new_purchase_shows_device_step_with_smallest_last(monkeypatch):
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)
    tariff = _tariff()
    monkeypatch.setattr(tp, 'get_tariff_by_id', AsyncMock(return_value=tariff))
    monkeypatch.setattr(tp, 'get_subscription_by_user_id', AsyncMock(return_value=None))

    async def price(t, period, device_limit=None, **kw):
        total = 31000 + (device_limit - 3) * 5900
        return SimpleNamespace(final_total=total, original_total=total)

    monkeypatch.setattr('app.services.pricing_engine.pricing_engine.calculate_tariff_purchase_price', price)
    callback = SimpleNamespace(
        data='tariff_period:3:30', answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock())
    )
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    user = SimpleNamespace(id=1, language='ru', balance_kopeks=0)

    await tp.select_tariff_period(callback, user, AsyncMock(), state)

    rows = callback.message.edit_text.await_args.kwargs['reply_markup'].inline_keyboard
    got = [(r[0].callback_data, r[0].style, r[0].text) for r in rows]
    assert [g[:2] for g in got] == [
        ('tariff_dev:3:30:5', 'success'),
        ('tariff_dev:3:30:7', 'success'),
        ('tariff_dev:3:30:10', 'success'),
        ('tariff_dev:3:30:3', None),
        ('tariff_select:3', None),
    ]
    assert got[0][2] == '5 устройств — 428 ₽'
    assert got[3][2] == '3 устройства'


async def test_picked_devices_go_to_state_and_back_to_the_period_screen(monkeypatch):
    seen = {}

    async def fake_period(callback, user, db, state):
        seen['data'] = callback.data
        seen['chosen'] = (await state.get_data())['chosen_devices']

    monkeypatch.setattr(tp, 'select_tariff_period', fake_period)
    callback = SimpleNamespace(
        data='tariff_dev:3:30:7', answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock())
    )
    callback.model_copy = lambda update: SimpleNamespace(**{**callback.__dict__, **update})
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))

    await tp.select_tariff_devices(callback, SimpleNamespace(id=1, language='ru'), AsyncMock(), state)

    assert seen == {'data': 'tariff_period:3:30', 'chosen': {'tariff_id': 3, 'period': 30, 'devices': 7}}


def test_no_device_step_for_periods_that_are_not_whole_months():
    tariff = _tariff()
    assert offers_device_choice(tariff, None, 30)
    assert offers_device_choice(tariff, None, 90)
    assert not offers_device_choice(tariff, None, 14)


def test_autopay_keyboard_shows_only_the_useful_toggle():
    from app.keyboards.inline import get_autopay_keyboard

    def cbs(enabled):
        return [b.callback_data for row in get_autopay_keyboard('ru', enabled=enabled).inline_keyboard for b in row]

    assert 'autopay_enable' in cbs(False) and 'autopay_disable' not in cbs(False)
    assert 'autopay_disable' in cbs(True) and 'autopay_enable' not in cbs(True)
