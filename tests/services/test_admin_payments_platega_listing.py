"""Разовые платежи Platega в админке платежей.

Строка в ``platega_payments`` показывается ровно один раз, а номер платежа
открывает именно его, а не транзакцию с тем же id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.database.models import (
    Base,
    PaymentMethod,
    PlategaPayment,
    Transaction,
    TransactionType,
    User,
)
from app.services.payment_verification_service import (
    get_payment_record,
    list_recent_pending_payments,
)
from tests.fixtures.sqlite_memory import memory_session


# Загрузчик опрашивает таблицы всех провайдеров сразу, поэтому поднимаем
# полную схему: список «только нужных» таблиц пришлось бы править при каждом
# новом шлюзе, а тест падал бы с невнятным «no such table».
TABLES = list(Base.metadata.tables.values())


def _user(user_id: int = 1) -> User:
    return User(
        id=user_id,
        telegram_id=1000 + user_id,
        first_name=f'U{user_id}',
        language='ru',
        status='active',
        balance_kopeks=0,
    )


def _platega_deposit(*, user_id: int = 1, external_id: str, **over) -> Transaction:
    """Транзакция пополнения, какую пишет вебхук разовой оплаты Platega."""
    fields = {
        'user_id': user_id,
        'type': TransactionType.DEPOSIT.value,
        'amount_kopeks': 50000,
        'description': 'Пополнение через Platega',
        'payment_method': PaymentMethod.PLATEGA.value,
        'external_id': external_id,
        'is_completed': True,
        'created_at': datetime.now(UTC) - timedelta(hours=1),
    }
    fields.update(over)
    return Transaction(**fields)


@pytest.mark.asyncio
async def test_ordinary_platega_topup_is_not_duplicated(monkeypatch) -> None:
    """Пополнение через Platega видно по своей строке в platega_payments — один раз."""
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(
            [
                _user(),
                PlategaPayment(
                    id=1,
                    user_id=1,
                    amount_kopeks=50000,
                    status='PENDING',
                    is_paid=False,
                    created_at=datetime.now(UTC) - timedelta(minutes=5),
                    platega_transaction_id='tx-1',
                    correlation_id='corr-1',
                    payment_method_code=2,
                ),
                _platega_deposit(external_id='tx-1'),
            ]
        )
        await db.commit()

        records = await list_recent_pending_payments(db)

    assert [r.method for r in records].count(PaymentMethod.PLATEGA) == 1


@pytest.mark.asyncio
async def test_pending_platega_payment_still_listed(monkeypatch) -> None:
    """Существующая логика pending-платежей не изменилась."""
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(
            [
                _user(),
                PlategaPayment(
                    id=7,
                    user_id=1,
                    amount_kopeks=50000,
                    status='PENDING',
                    is_paid=False,
                    created_at=datetime.now(UTC) - timedelta(minutes=5),
                    platega_transaction_id='tx-pending',
                    correlation_id='corr-pending',
                    payment_method_code=2,
                ),
            ]
        )
        await db.commit()

        records = await list_recent_pending_payments(db)

    pending = [r for r in records if r.method == PaymentMethod.PLATEGA]
    assert len(pending) == 1
    assert pending[0].identifier == 'tx-pending'
    assert pending[0].is_paid is False


@pytest.mark.asyncio
async def test_details_do_not_confuse_ids_between_tables(monkeypatch) -> None:
    """Детали ``/platega/{payment_id}`` открывают строку platega_payments, а не транзакцию с тем же id."""
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(
            [
                _user(1),
                _user(2),
                # Обе записи получают id = 1, но в разных таблицах.
                _platega_deposit(id=1, user_id=1, external_id='tx-own'),
                PlategaPayment(
                    id=1,
                    user_id=2,
                    amount_kopeks=50000,
                    status='PENDING',
                    is_paid=False,
                    created_at=datetime.now(UTC) - timedelta(minutes=5),
                    platega_transaction_id='tx-other',
                    correlation_id='corr-other',
                    payment_method_code=2,
                ),
            ]
        )
        await db.commit()

        provider = await get_payment_record(db, PaymentMethod.PLATEGA, 1)

        assert provider is not None
        assert provider.identifier == 'tx-other'
        assert provider.user.id == 2
