"""Списание Platega по удалённой подписке: отмена у Platega, деньги на баланс, алерт админу.

Раньше коллбек по неизвестному/осиротевшему SubscriptionId только логировал
warning и отвечал 200 — Platega списывала дальше, услуги не было.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.database.crud import platega_subscription as sub_crud
from app.database.models import (
    Base,
    PaymentMethod,
    PlategaSubscription,
    Subscription,
    Transaction,
    TransactionType,
    User,
)
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


def _svc():
    from app.services.payment.platega import PlategaPaymentMixin

    class Svc(PlategaPaymentMixin):
        def __init__(self):
            self.platega_service = SimpleNamespace(cancel_subscription=AsyncMock(return_value={'status': 'cancelled'}))

    return Svc()


async def _user(db, *, user_id=1, balance=0):
    db.add(User(id=user_id, telegram_id=1000 + user_id, first_name='U', language='ru', balance_kopeks=balance))
    await db.commit()


async def _deposits(db):
    return (
        (await db.execute(select(Transaction).where(Transaction.type == TransactionType.DEPOSIT.value))).scalars().all()
    )


@pytest.mark.asyncio
async def test_charge_for_deleted_subscription_cancels_credits_and_alerts(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _user(db, balance=500)
        db.add(Subscription(id=10, user_id=1, status='active', end_date=datetime.now(UTC) + timedelta(days=2)))
        await db.commit()
        rec = await sub_crud.create_platega_subscription(
            db,
            user_id=1,
            subscription_id=10,
            tariff_id=None,
            interval=3,
            charge_days=30,
            amount_kopeks=19900,
            redirect_url=None,
            platega_subscription_id='ps-1',
            status='ACTIVE',
        )

        # Подписку удалили (ORM-путь, как в админке): запись привязки остаётся
        # с subscription_id = NULL, а не исчезает каскадом.
        await db.delete(await db.get(Subscription, 10))
        await db.commit()
        await db.refresh(rec)
        assert rec.subscription_id is None

        svc = _svc()
        payload = {'Status': 'CONFIRMED', 'Id': 'charge-1', 'Amount': 199, 'SubscriptionId': 'ps-1'}
        with patch('app.services.payment.platega.alert_payment_not_applied', AsyncMock()) as alert:
            await svc.process_platega_subscription_callback(db, payload)
            # Ретрай того же коллбека: ни второго зачисления, ни второго алерта.
            await svc.process_platega_subscription_callback(db, payload)

        svc.platega_service.cancel_subscription.assert_awaited_once_with('ps-1')
        await db.refresh(rec)
        assert rec.status == 'CANCELLED'
        assert rec.charges_success == 0
        assert rec.last_charge_external_id == 'charge-1'

        user = await db.get(User, 1)
        await db.refresh(user)
        assert user.balance_kopeks == 500 + 19900
        deposits = await _deposits(db)
        assert [(d.amount_kopeks, d.external_id, d.payment_method) for d in deposits] == [
            (19900, 'charge-1', PaymentMethod.PLATEGA.value)
        ]

        alert.assert_awaited_once()
        kwargs = alert.await_args.kwargs
        assert kwargs['user_id'] == 1
        assert kwargs['amount_kopeks'] == 19900
        assert kwargs['details']['SubscriptionId'] == 'ps-1'
        assert 'зачислена' in kwargs['problem']


@pytest.mark.asyncio
async def test_charge_for_unknown_binding_uses_payload_token_for_user(monkeypatch):
    """Записи нет совсем (снесена до миграции 0140): пользователь — из payload-токена,
    сумма — из коллбека."""
    async with memory_session(monkeypatch, TABLES) as db:
        await _user(db, user_id=7)
        svc = _svc()
        payload = {
            'status': 'CONFIRMED',
            'id': 'charge-x',
            'amount': '149.50',
            'subscriptionId': 'ps-gone',
            'payload': 'platega-sub:7:55:abcd1234',
        }
        with patch('app.services.payment.platega.alert_payment_not_applied', AsyncMock()) as alert:
            await svc.process_platega_subscription_callback(db, payload)
            await svc.process_platega_subscription_callback(db, payload)

        svc.platega_service.cancel_subscription.assert_awaited_with('ps-gone')
        user = await db.get(User, 7)
        await db.refresh(user)
        assert user.balance_kopeks == 14950
        assert len(await _deposits(db)) == 1
        alert.assert_awaited_once()
        assert alert.await_args.kwargs['user_id'] == 7


@pytest.mark.asyncio
async def test_charge_for_unknown_binding_without_user_alerts_without_credit(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        svc = _svc()
        with patch('app.services.payment.platega.alert_payment_not_applied', AsyncMock()) as alert:
            await svc.process_platega_subscription_callback(
                db, {'Status': 'CONFIRMED', 'Id': 'charge-y', 'Amount': 199, 'SubscriptionId': 'ps-none'}
            )

        svc.platega_service.cancel_subscription.assert_awaited_once_with('ps-none')
        assert await _deposits(db) == []
        alert.assert_awaited_once()
        kwargs = alert.await_args.kwargs
        assert kwargs['user_id'] is None
        assert kwargs['amount_kopeks'] == 19900
        assert 'НЕ зачислены' in kwargs['problem']


@pytest.mark.asyncio
async def test_non_charge_status_for_unknown_binding_stays_quiet(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        svc = _svc()
        with patch('app.services.payment.platega.alert_payment_not_applied', AsyncMock()) as alert:
            await svc.process_platega_subscription_callback(
                db, {'Status': 'SUBSCRIPTION_CANCELLED', 'SubscriptionId': 'ps-none'}
            )
        svc.platega_service.cancel_subscription.assert_not_awaited()
        alert.assert_not_awaited()


def test_model_fk_is_set_null_and_nullable():
    column = PlategaSubscription.__table__.c.subscription_id
    assert column.nullable is True
    (fk,) = column.foreign_keys
    assert fk.ondelete == 'SET NULL'


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'm0140', Path('migrations/alembic/versions/0140_platega_sub_fk_set_null.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0140_upgrade_downgrade_idempotent():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _load_migration()
    assert (module.revision, module.down_revision) == ('0140', '0139')

    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE subscriptions (id INTEGER PRIMARY KEY)'))
        conn.execute(
            sa.text(
                'CREATE TABLE platega_subscriptions (id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL, '
                'status VARCHAR(20), CONSTRAINT platega_subscriptions_subscription_id_fkey FOREIGN KEY '
                '(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE)'
            )
        )
        conn.execute(sa.text('INSERT INTO subscriptions VALUES (1)'))
        conn.execute(sa.text("INSERT INTO platega_subscriptions VALUES (1, 1, 'ACTIVE')"))

        def state():
            inspector = sa.inspect(conn)
            fks = [fk for fk in inspector.get_foreign_keys('platega_subscriptions')]
            column = next(c for c in inspector.get_columns('platega_subscriptions') if c['name'] == 'subscription_id')
            return [str(fk['options'].get('ondelete')).upper() for fk in fks], bool(column['nullable'])

        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            assert state() == (['SET NULL'], True)
            module.upgrade()  # повторный прогон — без изменений и без ошибок
            assert state() == (['SET NULL'], True)

        conn.execute(sa.text("INSERT INTO platega_subscriptions VALUES (2, NULL, 'ACTIVE')"))
        assert conn.execute(sa.text('SELECT count(*) FROM platega_subscriptions')).scalar() == 2

        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()
            assert state() == (['CASCADE'], False)
            module.downgrade()
            assert state() == (['CASCADE'], False)
        # Строка-сирота удалена (её снёс бы CASCADE), живая привязка осталась.
        assert conn.execute(sa.text('SELECT id FROM platega_subscriptions')).scalars().all() == [1]
