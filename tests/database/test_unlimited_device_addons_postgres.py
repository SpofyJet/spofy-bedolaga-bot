"""Adding slots must never replace an already paid unlimited device allowance."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.cabinet.routes.subscription_modules import devices
from app.cabinet.schemas.subscription import DevicePurchaseRequest
from app.config import settings
from app.database.models import Base, Subscription, Tariff, Transaction, User
from app.handlers.subscription import devices as telegram_devices
from app.services import subscription_auto_purchase_service as auto
from app.services.subscription_service import SubscriptionService
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres


@pytest.mark.parametrize('entry', ['price', 'cart', 'purchase', 'auto'])
async def test_unlimited_devices_cannot_be_sold_additional_slots(
    postgres_database, monkeypatch, entry, race=False, concurrent_limit=0
):
    monkeypatch.setattr(settings, 'PRICE_PER_DEVICE', 1000)
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 10)
    monkeypatch.setattr(devices, 'user_cart_service', SimpleNamespace(save_user_cart=AsyncMock()))
    monkeypatch.setattr(auto, '_delete_cart_for_subscription', AsyncMock())
    monkeypatch.setattr(SubscriptionService, 'update_remnawave_user', AsyncMock())
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user = User(id=1, telegram_id=100001, language='ru', status='active', balance_kopeks=100000)
        db.add(user)
        db.add(
            Tariff(
                id=1,
                name='Test',
                device_limit=2,
                device_price_kopeks=1000,
                max_device_limit=10,
                period_prices={'30': 10000},
            )
        )
        await db.flush()
        sub = Subscription(
            user_id=1,
            tariff_id=1,
            status='active',
            is_trial=False,
            device_limit=3 if race else 0,
            end_date=datetime.now(UTC) + timedelta(days=30),
            traffic_limit_gb=100,
        )
        db.add(sub)
        await db.commit()
        if race:
            from app.database.crud import user as user_crud

            original_debit = user_crud.subtract_user_balance

            async def change_to_unlimited_after_debit(*args, **kwargs):
                result = await original_debit(*args, **kwargs)
                sub.device_limit = concurrent_limit
                await db.commit()
                return result

            monkeypatch.setattr(user_crud, 'subtract_user_balance', change_to_unlimited_after_debit)
            monkeypatch.setattr(telegram_devices, 'subtract_user_balance', change_to_unlimited_after_debit)
        if entry == 'telegram_change':
            monkeypatch.setattr(telegram_devices, '_resolve_subscription', AsyncMock(return_value=(sub, sub.id)))
            callback = SimpleNamespace(data='change_devices_confirm_4', answer=AsyncMock())
            await telegram_devices.execute_change_devices(callback, user, db)
            callback.answer.assert_awaited_once()
        elif entry == 'auto':
            outcome = await auto._auto_add_devices(
                db, user, {'devices_to_add': 1, 'price_kopeks': 1000, 'subscription_id': sub.id}
            )
            assert outcome is False
        elif entry == 'price':
            result = await devices.get_device_price(devices=1, subscription_id=sub.id, user=user, db=db)
            assert result['available'] is False
        else:
            handler = {
                'cart': devices.save_devices_cart,
                'purchase': devices.purchase_devices,
            }[entry]
            with pytest.raises(HTTPException) as error:
                await handler(request=DevicePurchaseRequest(devices=1), subscription_id=sub.id, user=user, db=db)
            assert error.value.status_code == (409 if race else 400)
        await db.refresh(user)
        await db.refresh(sub)
        assert user.balance_kopeks == 100000
        assert sub.device_limit == (concurrent_limit if race else 0)
        transactions = list(await db.scalars(select(Transaction)))
        if race:
            assert len(transactions) == 2
            assert {row.type for row in transactions} == {'subscription_payment', 'refund'}
            assert sum(row.amount_kopeks for row in transactions) == 0
        else:
            assert transactions == []
        devices.user_cart_service.save_user_cart.assert_not_awaited()


# Автопокупка из корзины ('auto') держит строки пользователя и подписки под FOR UPDATE от
# проверки до одного общего коммита списания и лимита — окна «после списания» у неё нет,
# конкурентная смена лимита ждёт коммита (см. test_atomic_addon_cart_panel_down_postgres.py).
_RACE_ENTRIES = ['purchase', 'telegram_change']


@pytest.mark.parametrize('entry', _RACE_ENTRIES)
async def test_unlimited_granted_after_debit_refunds_and_preserves_limit(postgres_database, monkeypatch, entry):
    await test_unlimited_devices_cannot_be_sold_additional_slots(postgres_database, monkeypatch, entry, race=True)


@pytest.mark.parametrize('entry', _RACE_ENTRIES)
async def test_concurrent_device_increase_refunds_with_balanced_ledger(postgres_database, monkeypatch, entry):
    await test_unlimited_devices_cannot_be_sold_additional_slots(
        postgres_database, monkeypatch, entry, race=True, concurrent_limit=10
    )


async def test_auto_device_purchase_holds_subscription_lock_through_debit(postgres_database, monkeypatch):
    """Автопокупка: между списанием и выдачей чужая транзакция не может поменять лимит подписки."""
    from sqlalchemy import text, update
    from sqlalchemy.exc import DBAPIError

    from app.database.crud import user as user_crud
    from tests.fixtures.postgres_db import postgres_sessions

    monkeypatch.setattr(settings, 'PRICE_PER_DEVICE', 1000)
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 10)
    monkeypatch.setattr(auto, '_delete_cart_for_subscription', AsyncMock())
    monkeypatch.setattr(SubscriptionService, 'update_remnawave_user', AsyncMock())
    async with postgres_sessions(postgres_database, list(Base.metadata.sorted_tables), count=2) as (db, other):
        user = User(id=1, telegram_id=100001, language='ru', status='active', balance_kopeks=100000)
        db.add(user)
        db.add(
            Tariff(
                id=1,
                name='Test',
                device_limit=2,
                device_price_kopeks=1000,
                max_device_limit=10,
                period_prices={'30': 10000},
            )
        )
        await db.flush()
        sub = Subscription(
            user_id=1,
            tariff_id=1,
            status='active',
            is_trial=False,
            device_limit=3,
            end_date=datetime.now(UTC) + timedelta(days=30),
            traffic_limit_gb=100,
        )
        db.add(sub)
        await db.commit()
        sub_id = sub.id

        original_debit = user_crud.subtract_user_balance
        blocked = []

        async def debit_then_try_concurrent_change(*args, **kwargs):
            result = await original_debit(*args, **kwargs)
            await other.execute(text("SET LOCAL lock_timeout = '300ms'"))
            try:
                await other.execute(update(Subscription).where(Subscription.id == sub_id).values(device_limit=0))
            except DBAPIError as error:
                blocked.append('lock timeout' in str(error).lower())
            await other.rollback()
            return result

        monkeypatch.setattr(user_crud, 'subtract_user_balance', debit_then_try_concurrent_change)

        outcome = await auto._auto_add_devices(
            db, user, {'devices_to_add': 1, 'price_kopeks': 1000, 'subscription_id': sub_id}
        )

        assert blocked == [True], 'строка подписки не заблокирована между списанием и выдачей'
        assert outcome is True
        await db.refresh(user)
        refreshed = await db.get(Subscription, sub_id, populate_existing=True)
        assert refreshed.device_limit == 4
        assert user.balance_kopeks == 100000 - 1000
        transactions = list(await db.scalars(select(Transaction)))
        assert [(row.type, row.amount_kopeks) for row in transactions] == [('subscription_payment', -1000)]
