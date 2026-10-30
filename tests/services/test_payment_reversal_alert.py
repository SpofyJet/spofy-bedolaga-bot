"""Возврат/чарджбэк по уже оплаченному платежу: is_paid не сбрасывается, админ оповещён."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.database.crud.platega as platega_crud
import app.services.payment.platega as platega_module
import app.services.payment_service as payment_service_module
from app.services.payment_service import PaymentService


def _service() -> PaymentService:
    service = PaymentService.__new__(PaymentService)  # type: ignore[call-arg]
    service.bot = None
    service.platega_service = None
    return service


def _paid_payment() -> SimpleNamespace:
    return SimpleNamespace(
        id=11, user_id=7, amount_kopeks=50_000, is_paid=True, correlation_id='c-1', platega_transaction_id='tx-1'
    )


@pytest.mark.anyio('asyncio')
@pytest.mark.parametrize('status', ['CHARGEBACKED', 'FAILED', 'CANCELED'])
async def test_paid_platega_payment_reversal_alerts_and_keeps_is_paid(monkeypatch, status) -> None:
    payment = _paid_payment()
    monkeypatch.setattr(
        payment_service_module, 'get_platega_payment_by_transaction_id', AsyncMock(return_value=payment)
    )
    monkeypatch.setattr(platega_crud, 'get_platega_payment_by_id_for_update', AsyncMock(return_value=payment))
    update = AsyncMock()
    monkeypatch.setattr(payment_service_module, 'update_platega_payment', update)
    alert = AsyncMock()
    monkeypatch.setattr(platega_module, 'alert_paid_payment_reversed', alert)

    ok = await _service().process_platega_webhook(AsyncMock(), {'id': 'tx-1', 'status': status})

    assert ok is True
    assert 'is_paid' not in update.await_args.kwargs, 'повторный CONFIRMED финализировал бы платёж ещё раз'
    alert.assert_awaited_once()
    assert alert.await_args.kwargs['status'] == status


@pytest.mark.anyio('asyncio')
async def test_late_pending_on_paid_payment_is_not_an_alert(monkeypatch) -> None:
    payment = _paid_payment()
    monkeypatch.setattr(
        payment_service_module, 'get_platega_payment_by_transaction_id', AsyncMock(return_value=payment)
    )
    monkeypatch.setattr(platega_crud, 'get_platega_payment_by_id_for_update', AsyncMock(return_value=payment))
    monkeypatch.setattr(payment_service_module, 'update_platega_payment', AsyncMock())
    alert = AsyncMock()
    monkeypatch.setattr(platega_module, 'alert_paid_payment_reversed', alert)

    await _service().process_platega_webhook(AsyncMock(), {'id': 'tx-1', 'status': 'PENDING'})

    alert.assert_not_awaited()
