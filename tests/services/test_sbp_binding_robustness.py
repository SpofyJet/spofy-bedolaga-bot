"""СБП-автопродление: ошибка после предупреждения о смене способа видна, брошенная привязка не отдаёт старую ссылку.

* Предупреждение «Lava/баланс будут отключены» уже ответило на нажатие: второй
  answer() Telegram отвергает, и человек видел только предупреждение.
* PENDING-привязка, брошенная давно, возвращала ту же ссылку на форму банка
  бесконечно (сверка с TTL 48 ч не идёт при закрытом Subscription API).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.handlers.subscription.autopay as autopay_mod
from app.config import settings
from app.database.crud import platega_subscription as sub_crud
from app.database.models import PlategaSubscription, Subscription
from tests.fixtures.sqlite_memory import memory_session


def _gate_on(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'PLATEGA_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_MERCHANT_ID', 'm', raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_SECRET', 's', raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_RECURRENT_ENABLED', True, raising=False)


def _callback():
    callback = MagicMock()
    callback.message = MagicMock(spec=autopay_mod.types.Message)
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = 'sbp_recurring_enable_for:10'
    return callback


def _with_engine_warning(monkeypatch):
    monkeypatch.setattr(
        'app.services.recurrent_amount.get_active_recurrent_engines', AsyncMock(return_value=['balance'])
    )
    monkeypatch.setattr(
        'app.services.recurrent_amount.recurrent_engines_warning',
        lambda texts, engines, enabling: 'Автопродление с баланса будет отключено',
    )


@pytest.mark.parametrize('entry', ['menu', 'offer'])
@pytest.mark.asyncio
async def test_error_after_engine_warning_is_sent_as_message(monkeypatch, entry):
    _gate_on(monkeypatch)
    _with_engine_warning(monkeypatch)
    subscription = SimpleNamespace(id=10, user_id=1, tariff=SimpleNamespace(id=5), is_trial=False)
    monkeypatch.setattr(autopay_mod, '_resolve_subscription', AsyncMock(return_value=(subscription, 10)))
    monkeypatch.setattr('app.database.crud.subscription.get_subscription_by_id', AsyncMock(return_value=subscription))
    monkeypatch.setattr(
        'app.services.payment.platega.enable_platega_sbp_recurring',
        AsyncMock(side_effect=RuntimeError('platega down')),
    )
    callback = _callback()
    user = SimpleNamespace(id=1, language='ru')

    handler = (
        autopay_mod.handle_sbp_recurring_enable if entry == 'menu' else autopay_mod.handle_sbp_recurring_enable_for
    )
    await handler(callback, user, AsyncMock())

    callback.answer.assert_awaited_once()  # одно предупреждение — один ответ на нажатие
    assert 'будет отключено' in callback.answer.await_args.args[0]
    callback.message.answer.assert_awaited_once()
    assert 'Не удалось подключить автопродление' in callback.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_value_error_after_warning_is_escaped_in_message(monkeypatch):
    _gate_on(monkeypatch)
    _with_engine_warning(monkeypatch)
    subscription = SimpleNamespace(id=10, tariff=SimpleNamespace(id=5), is_trial=False)
    monkeypatch.setattr(autopay_mod, '_resolve_subscription', AsyncMock(return_value=(subscription, 10)))
    monkeypatch.setattr(
        'app.services.payment.platega.enable_platega_sbp_recurring',
        AsyncMock(side_effect=ValueError('цена <нет>')),
    )
    callback = _callback()

    await autopay_mod.handle_sbp_recurring_enable(callback, SimpleNamespace(id=1, language='ru'), AsyncMock())

    callback.message.answer.assert_awaited_once_with('цена &lt;нет&gt;')


@pytest.mark.asyncio
async def test_success_after_warning_does_not_answer_twice(monkeypatch):
    _gate_on(monkeypatch)
    _with_engine_warning(monkeypatch)

    async def _edit(callback, text, keyboard, parse_mode='HTML', **_):
        await callback.message.edit_text(text, reply_markup=keyboard)

    monkeypatch.setattr(autopay_mod, 'edit_or_answer_photo', _edit)
    subscription = SimpleNamespace(id=10, tariff=SimpleNamespace(id=5), is_trial=False)
    monkeypatch.setattr(autopay_mod, '_resolve_subscription', AsyncMock(return_value=(subscription, 10)))
    monkeypatch.setattr(
        'app.services.payment.platega.enable_platega_sbp_recurring',
        AsyncMock(return_value={'redirect_url': 'https://pay.platega.io/subscription/1', 'amount_kopeks': 27000}),
    )
    callback = _callback()

    await autopay_mod.handle_sbp_recurring_enable(callback, SimpleNamespace(id=1, language='ru'), AsyncMock())

    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()


def _tariff():
    return SimpleNamespace(
        id=5,
        is_daily=False,
        name='Стандарт',
        get_available_periods=lambda: [30],
        get_shortest_period=lambda: 30,
        get_purchasable_price_for_period=lambda days: 19900,
    )


def _service(link: str):
    from app.services.payment.platega import PlategaPaymentMixin

    class Svc(PlategaPaymentMixin):
        def __init__(self):
            self.platega_service = SimpleNamespace(
                create_subscription=AsyncMock(
                    return_value={'transactionId': 'tx-new', 'redirect': link, 'status': 'PENDING'}
                ),
                cancel_subscription=AsyncMock(return_value={}),
            )

    return Svc()


async def _pending(db, *, minutes_ago: int) -> PlategaSubscription:
    record = await sub_crud.create_platega_subscription(
        db,
        user_id=777,
        subscription_id=1,
        tariff_id=5,
        platega_subscription_id='tx-old',
        interval=3,
        charge_days=30,
        amount_kopeks=19900,
        status='PENDING',
        redirect_url='https://pay.platega.io/subscription/old',
    )
    record.created_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    await db.commit()
    return record


TABLES = [PlategaSubscription.__table__, Subscription.__table__]


@pytest.mark.asyncio
async def test_fresh_pending_binding_keeps_its_link(monkeypatch):
    subscription = SimpleNamespace(id=1, autopay_enabled=False, autopay_period_days=30)
    async with memory_session(monkeypatch, TABLES) as db:
        await _pending(db, minutes_ago=5)
        svc = _service('https://pay.platega.io/subscription/new')

        result = await svc.create_platega_sbp_subscription(db, user_id=777, subscription=subscription, tariff=_tariff())

    assert result['redirect_url'] == 'https://pay.platega.io/subscription/old'
    svc.platega_service.create_subscription.assert_not_awaited()
    svc.platega_service.cancel_subscription.assert_not_awaited()


@pytest.mark.asyncio
async def test_abandoned_pending_binding_gets_a_fresh_link(monkeypatch):
    subscription = SimpleNamespace(id=1, autopay_enabled=False, autopay_period_days=30)
    async with memory_session(monkeypatch, TABLES) as db:
        old = await _pending(db, minutes_ago=90)
        svc = _service('https://pay.platega.io/subscription/new')

        result = await svc.create_platega_sbp_subscription(db, user_id=777, subscription=subscription, tariff=_tariff())

        assert result['redirect_url'] == 'https://pay.platega.io/subscription/new'
        svc.platega_service.cancel_subscription.assert_awaited_once_with('tx-old')
        await db.refresh(old)
        assert old.status == 'CANCELLED'
