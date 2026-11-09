"""Cabinet top-up keeps provider limits."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.cabinet.routes import balance
from app.cabinet.schemas.balance import PaymentMethodResponse


pytestmark = pytest.mark.anyio


def _method(method_id, minimum=100):
    return PaymentMethodResponse(
        id=method_id,
        name=method_id,
        min_amount_kopeks=minimum,
        max_amount_kopeks=100_000,
        is_available=True,
    )


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def checkout(monkeypatch):
    user = SimpleNamespace(id=42, telegram_id=None, username=None, email='user@example.com', language='ru')
    service = SimpleNamespace(create_platega_payment=AsyncMock(), create_pay2328_payment=AsyncMock())
    methods = []

    async def get_methods(**kwargs):
        return methods

    monkeypatch.setattr(balance, 'get_payment_methods', get_methods)
    monkeypatch.setattr(balance, 'PaymentService', lambda: service)
    application = FastAPI()
    application.include_router(balance.router)
    application.dependency_overrides[balance.get_current_cabinet_user] = lambda: user
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: False)), commit=AsyncMock())
    application.dependency_overrides[balance.get_cabinet_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=application), base_url='https://cabinet.example') as client:
        yield client, methods, service


@pytest.mark.parametrize('provider', ['platega', 'wata', 'pay2328', 'cryptobot'])
async def test_lower_schema_bound_does_not_bypass_provider_minimum(checkout, provider):
    client, methods, service = checkout
    methods.append(_method(provider, minimum=2000))
    response = await client.post('/balance/topup', json={'amount_kopeks': 100, 'payment_method': provider})
    assert response.status_code == 400
    assert response.json()['detail'] == 'Minimum amount is 20.00 RUB'
    assert not service.create_platega_payment.called
    assert not service.create_pay2328_payment.called


@pytest.mark.parametrize('amount', [0, -1])
async def test_nonpositive_topup_remains_invalid(checkout, amount):
    client, _, _ = checkout
    response = await client.post('/balance/topup', json={'amount_kopeks': amount, 'payment_method': 'platega'})
    assert response.status_code == 422


async def test_unavailable_method_rejected_before_payment_creation(checkout):
    client, _, service = checkout
    response = await client.post('/balance/topup', json={'amount_kopeks': 100, 'payment_method': 'platega'})
    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid or unavailable payment method'
    assert not service.create_platega_payment.called
