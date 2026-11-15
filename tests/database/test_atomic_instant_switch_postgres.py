"""Мгновенная смена тарифа с доплатой — на PostgreSQL.

Доплата коммитилась отдельно и раньше всего остального: смена тарифа — следующим
коммитом, запись о платеже — третьим, уже после панели и сброса устройств. Сбой между
ними оставлял списание без смены тарифа или без записи о платеже (02.11.2026 во время
сбоя панели: 55,50 ₽ списаны, записи нет). А когда панель не отвечала, её сервис
откатывал сессию и возвращал None — исключения нет, и оплаченный тариф (серверы,
трафик) в очередь повторов не ставился: в панели оставался старый.

Здесь настоящие обработчик, сервис панели и база; не отвечает только панель (502).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Transaction, User
from app.handlers.subscription import tariff_purchase as telegram
from app.localization.texts import get_texts
from app.services.remnawave_retry_queue import remnawave_retry_queue
from tests.fixtures.postgres_db import postgres_session
from tests.handlers.test_panel_down_after_charge import (  # noqa: F401 — фикстуры
    BYPASS_ID,
    STANDARD_ID,
    SUB_ID,
    USER_ID,
    _Callback,
    _payments,
    _seed,
    _spofy_mode,
    admin_chat,
    cart_service,
    confirm_instant_switch,
    panel_down,
    state,
)


pytestmark = pytest.mark.postgres

TABLES = list(Base.metadata.sorted_tables)
BALANCE = 10000


@pytest.fixture
def retry_queue(monkeypatch) -> list[dict]:
    queued: list[dict] = []
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: queued.append(kwargs))
    return queued


@pytest.fixture(autouse=True)
def _upgrade_enabled(monkeypatch):
    monkeypatch.setattr(settings, 'TARIFF_SWITCH_UPGRADE_ENABLED', True)
    telegram._balance_checkouts_in_flight.clear()
    yield
    telegram._balance_checkouts_in_flight.clear()


async def test_paid_switch_while_panel_is_down_is_recorded_and_retried(
    postgres_database, cart_service, state, panel_down, admin_chat, retry_queue
):
    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db, balance=BALANCE)
        callback = _Callback(f'instant_sw_confirm:{BYPASS_ID}')

        await confirm_instant_switch(callback, await db.get(User, USER_ID), db, state)

        db.expire_all()
        charged = BALANCE - (await db.get(User, USER_ID)).balance_kopeks
        payments = await _payments(db)
        tariff_after = (await db.get(Subscription, SUB_ID)).tariff_id

    assert panel_down, 'до панели дошли — и она не ответила'
    assert charged > 0 and tariff_after == BYPASS_ID
    assert payments == [charged], 'списание записано в платежи'
    assert 'Тариф успешно изменён' in callback.shown
    assert [item['subscription_id'] for item in retry_queue] == [SUB_ID], 'оплаченный тариф дойдёт до панели'


async def test_switch_failure_after_charge_leaves_money_untouched(
    postgres_database, monkeypatch, cart_service, state, admin_chat, retry_queue
):
    """Сбой между доплатой и сменой тарифа — нет ни списания, ни смены (раньше: списано, тариф старый)."""
    from app.database.crud import subscription as subscription_crud

    async def broken(*args, **kwargs):
        raise RuntimeError('deadlock detected')

    monkeypatch.setattr(subscription_crud, '_apply_base_limit_preserving_active_purchases', broken)
    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db, balance=BALANCE)
        callback = _Callback(f'instant_sw_confirm:{BYPASS_ID}')

        await confirm_instant_switch(callback, await db.get(User, USER_ID), db, state)
        # Как middleware бота: после обработчика — commit того, что осталось в сессии.
        await db.commit()

        db.expire_all()
        balance = (await db.get(User, USER_ID)).balance_kopeks
        payments = await _payments(db)
        tariff_after = (await db.get(Subscription, SUB_ID)).tariff_id

    assert (balance, payments, tariff_after) == (BALANCE, [], STANDARD_ID), 'ни списания, ни смены тарифа'
    assert callback.shown == get_texts('ru').t('TARIFF_SWITCH_ERROR', '')


async def test_second_click_while_first_switch_is_charging_does_not_charge_again(
    postgres_database, monkeypatch, cart_service, state, admin_chat, retry_queue
):
    from sqlalchemy.ext.asyncio import AsyncSession

    held, release = asyncio.Event(), asyncio.Event()
    original = telegram.subtract_user_balance
    calls = 0

    async def first_charge_is_slow(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            held.set()
            await asyncio.wait_for(release.wait(), 10)
        return await original(*args, **kwargs)

    monkeypatch.setattr(telegram, 'subtract_user_balance', first_charge_is_slow)

    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db, balance=BALANCE)
        first_click = _Callback(f'instant_sw_confirm:{BYPASS_ID}')
        second_click = _Callback(f'instant_sw_confirm:{BYPASS_ID}')
        async with AsyncSession(db.bind, expire_on_commit=False, autoflush=False) as other_db:
            first = asyncio.create_task(confirm_instant_switch(first_click, await db.get(User, USER_ID), db, state))
            second = None
            try:
                await asyncio.wait_for(held.wait(), 5)
                second = asyncio.create_task(
                    confirm_instant_switch(second_click, await other_db.get(User, USER_ID), other_db, state)
                )
                await asyncio.wait({second}, timeout=1.0)
                release.set()
                await asyncio.wait_for(asyncio.gather(first, second), 15)
                await other_db.commit()
            finally:
                release.set()
                for task in (first, second):
                    if task and not task.done():
                        task.cancel()
                await asyncio.gather(*(t for t in (first, second) if t), return_exceptions=True)

        db.expire_all()
        charged = BALANCE - (await db.get(User, USER_ID)).balance_kopeks
        payments = list(
            (await db.execute(select(Transaction.amount_kopeks).where(Transaction.user_id == USER_ID))).scalars()
        )

    assert charged > 0 and [abs(p) for p in payments] == [charged], 'доплата списана один раз'
