"""Двойное нажатие «Подтвердить» в продлении и смене тарифа с баланса — на PostgreSQL.

Второе нажатие (троттлинг пропускает его через 0,5 с) вставало в очередь за блокировкой
строки пользователя, дожидалось коммита первого и списывало ещё раз: двойная цена за
двойной срок, которого человек не просил (05.10.2026: 209 ₽ ×2 с разницей 2,4 с).
Кнопка исчезает только когда первое нажатие отредактирует сообщение — после списания,
панели и уведомлений, — и всё это время второе нажатие доходило до денег.
"""

import asyncio
import inspect
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.user import get_user_by_id
from app.database.models import Tariff, Transaction
from app.handlers.subscription import tariff_purchase as telegram
from app.localization.texts import get_texts
from tests.database.tariff_checkout import checkout


pytestmark = pytest.mark.postgres


class _SkipRemovedSettings:
    """monkeypatch для общей заготовки checkout: настройки, которых в конфиге больше нет
    (SALES_MODE убран вместе с классическим режимом), пропускаются, остальное — как есть."""

    def __init__(self, monkeypatch):
        self._monkeypatch = monkeypatch

    def setattr(self, target, name, *args, **kwargs):
        if target is settings and isinstance(name, str) and not hasattr(settings, name):
            return None
        return self._monkeypatch.setattr(target, name, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._monkeypatch, name)


def _second_click(first) -> SimpleNamespace:
    return SimpleNamespace(
        data=first.data,
        answer=AsyncMock(),
        bot=SimpleNamespace(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )


async def _add_other_tariff(c, monkeypatch) -> None:
    monkeypatch.setattr(settings, 'TARIFF_SWITCH_UPGRADE_ENABLED', True)
    monkeypatch.setattr(settings, 'TARIFF_SWITCH_DOWNGRADE_ENABLED', True)
    monkeypatch.setattr(
        'app.services.remnawave_service.RemnaWaveService',
        lambda: SimpleNamespace(get_api_client=Mock(return_value=AsyncMock())),
    )
    c.db.add(
        Tariff(
            id=2,
            name='Other',
            is_active=True,
            traffic_limit_gb=200,
            device_limit=2,
            period_prices={'30': 25000},
            allowed_squads=['test-squad'],
        )
    )
    await c.db.commit()


@pytest.mark.parametrize(
    ('flow', 'callback_data', 'price'),
    [
        ('renewal', 'tariff_ext_confirm:10:1:30', 30000),
        ('switch', 'tariff_switch_confirm:2:30', 25000),
    ],
)
async def test_second_click_while_first_is_charging_does_not_charge_again(
    postgres_database, monkeypatch, flow, callback_data, price
):
    async with checkout(postgres_database, _SkipRemovedSettings(monkeypatch)) as c:
        handler = inspect.unwrap(
            telegram.confirm_tariff_extend if flow == 'renewal' else telegram.confirm_tariff_switch
        )
        if flow == 'switch':
            await _add_other_tariff(c, monkeypatch)
        c.callback.data = callback_data
        second_callback = _second_click(c.callback)

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

        async with AsyncSession(c.db.bind, expire_on_commit=False, autoflush=False) as other_db:
            second_user = await get_user_by_id(other_db, c.user.id)
            first = asyncio.create_task(handler(c.callback, c.user, c.db, c.state))
            second = None
            try:
                await asyncio.wait_for(held.wait(), 5)
                second = asyncio.create_task(handler(second_callback, second_user, other_db, c.state))
                # Даём второму нажатию дойти до блокировки (или ответить сразу).
                await asyncio.wait({second}, timeout=1.0)
                release.set()
                await asyncio.wait_for(asyncio.gather(first, second), 15)
            finally:
                release.set()
                for task in (first, second):
                    if task and not task.done():
                        task.cancel()
                await asyncio.gather(*(t for t in (first, second) if t), return_exceptions=True)

        await c.db.refresh(c.user)
        await c.db.refresh(c.sub)
        payments = list(await c.db.scalars(select(Transaction)))

    assert c.user.balance_kopeks == 400000 - price, 'списано один раз'
    assert [abs(p.amount_kopeks) for p in payments] == [price]
    if flow == 'renewal':
        assert c.sub.end_date == c.end + timedelta(days=30), 'продлено один раз'
    else:
        assert c.sub.tariff_id == 2
    alert = second_callback.answer.await_args
    assert alert is not None and alert.kwargs.get('show_alert') is True
    assert alert.args[0] == get_texts('ru').t('TARIFF_PURCHASE_IN_PROGRESS', ''), '«уже оформляется», без списания'


async def test_renewal_after_the_first_one_finished_still_charges(postgres_database, monkeypatch):
    """Осознанное второе продление (после того как первое закончилось) — как раньше, списывает."""
    async with checkout(postgres_database, _SkipRemovedSettings(monkeypatch)) as c:
        c.callback.data = 'tariff_ext_confirm:10:1:30'
        handler = inspect.unwrap(telegram.confirm_tariff_extend)
        await handler(c.callback, c.user, c.db, c.state)
        await handler(_second_click(c.callback), c.user, c.db, c.state)
        await c.db.refresh(c.user)
        await c.db.refresh(c.sub)
        payments = list(await c.db.scalars(select(Transaction)))

    assert c.user.balance_kopeks == 400000 - 2 * 30000
    assert len(payments) == 2
    assert c.sub.end_date == c.end + timedelta(days=60)
