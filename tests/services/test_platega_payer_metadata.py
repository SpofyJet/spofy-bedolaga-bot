"""Каждый платёж Platega несёт плательщика: metadata.userId и metadata.userName.

docs.platega.io: для части категорий магазинов оба поля обязательны; «отсутствие
metadata.userId при наличии требования отключает антифрод-защиту и может привести
к отключению магазина». v4.11 не передавала metadata ни в разовом платеже, ни на
лендинге.
"""

from __future__ import annotations

import hashlib
import types
from typing import Any

import pytest

from app.config import settings
from app.database.models import Base, GuestPurchase, User
from app.services.payment import platega as platega_mixin
from app.services.payment.payer_identity import PayerIdentity
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)
TOKEN = 'b' * 64


class _StubPlatega:
    is_configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_payment(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {'transactionId': 'tx', 'status': 'PENDING', 'redirect': 'https://pay'}


@pytest.fixture(autouse=True)
def _limits(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'PLATEGA_MIN_AMOUNT_KOPEKS', 1, raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_MAX_AMOUNT_KOPEKS', 10_000_000, raising=False)

    async def fake_persist(db, **kwargs):
        return types.SimpleNamespace(id=1)

    monkeypatch.setattr(
        platega_mixin.import_module('app.services.payment_service'), 'create_platega_payment', fake_persist
    )


async def _pay(db, *, user_id: int | None, payer: PayerIdentity | None = None) -> PayerIdentity:
    stub = _StubPlatega()
    mixin = platega_mixin.PlategaPaymentMixin()
    mixin.platega_service = stub
    extra = {'payer': payer} if payer is not None else {}
    result = await mixin.create_platega_payment(
        db,
        user_id=user_id,
        amount_kopeks=10_000,
        description='Пополнение',
        language='ru',
        payment_method_code=2,
        **extra,
    )
    assert result is not None
    return stub.calls[0]['payer']


@pytest.mark.asyncio
async def test_telegram_user_payment_carries_telegram_id_and_username(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=42, telegram_id=555, username='neo', language='ru', status='active'))
        await db.commit()

        payer = await _pay(db, user_id=42)

    assert payer.platega_metadata() == {'userId': '555', 'userName': '@neo', 'user_email': '555@telegram.org'}


@pytest.mark.asyncio
async def test_email_user_payment_carries_internal_id_and_email(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(
            User(id=43, telegram_id=None, auth_type='email', email='mail@example.com', language='ru', status='active')
        )
        await db.commit()

        payer = await _pay(db, user_id=43)

    assert payer.platega_metadata() == {
        'userId': 'user-43',
        'userName': 'mail@example.com',
        'user_email': 'mail@example.com',
    }


@pytest.mark.asyncio
async def test_explicit_payer_is_sent_as_is(monkeypatch) -> None:
    given = PayerIdentity(user_id='guest-x', user_name='guest@example.com', contact='guest@example.com')
    async with memory_session(monkeypatch, TABLES) as db:
        payer = await _pay(db, user_id=None, payer=given)

    assert payer == given


@pytest.mark.asyncio
async def test_payment_without_user_and_payer_is_still_filled(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        payer = await _pay(db, user_id=None)

    assert payer.user_id.startswith('guest-')
    assert payer.user_name


@pytest.mark.asyncio
async def test_landing_guest_payment_carries_the_guest(monkeypatch) -> None:
    import app.services.payment_service as payment_service_module

    captured: dict[str, Any] = {}

    async def fake_create_platega_payment(self, db, **kwargs):
        captured.update(kwargs)
        return {'redirect_url': 'https://pay', 'correlation_id': 'c', 'local_payment_id': 1}

    monkeypatch.setattr(payment_service_module.PaymentService, 'create_platega_payment', fake_create_platega_payment)
    monkeypatch.setattr(payment_service_module, '_GETTER_OVERRIDES', {}, raising=False)

    service = payment_service_module.PaymentService.__new__(payment_service_module.PaymentService)
    service.platega_service = types.SimpleNamespace()

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(
            GuestPurchase(
                token=TOKEN,
                contact_type='telegram',
                contact_value='@buyer',
                amount_kopeks=10_000,
                period_days=30,
                payment_method='platega_2',
                status='pending',
            )
        )
        await db.commit()

        await service.create_guest_payment(
            db,
            amount_kopeks=10_000,
            payment_method='platega_2',
            description='Подписка',
            purchase_token=TOKEN,
            return_url='https://example.com/ok',
        )

    guest_id = 'guest-' + hashlib.sha256(TOKEN.encode()).hexdigest()[:16]
    assert captured['payer'].platega_metadata() == {
        'userId': guest_id,
        'userName': '@buyer',
        'user_email': f'{guest_id}@spofyltd.ru',
    }
