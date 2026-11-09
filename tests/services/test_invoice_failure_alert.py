"""Алерт, когда провайдер не создаёт счета: блокировка сразу, сбои по порогу, без повторов."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services import payment_problem_alert as alerts
from app.services.payment_service import PaymentService


@pytest.fixture(autouse=True)
def clean_state():
    alerts._invoice_failures.clear()
    alerts._invoice_last_alert.clear()
    yield
    alerts._invoice_failures.clear()
    alerts._invoice_last_alert.clear()


@pytest.fixture
def send():
    with patch.object(alerts, '_send_to_admins', new=AsyncMock()) as mock:
        yield mock


async def test_blocked_provider_alerts_on_first_refusal(send):
    await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='423 METHOD_BLOCKED', blocked=True, user_id=7)

    send.assert_awaited_once()
    text = send.await_args.args[1]
    assert 'клиенты не могут оплатить' in text
    assert '423 METHOD_BLOCKED' in text
    assert 'Пользователь: 7' in text


async def test_ordinary_failures_need_threshold(send):
    for _ in range(alerts.INVOICE_FAILURE_THRESHOLD - 1):
        await alerts.alert_invoice_failed(None, provider='WATA', reason='timeout')
    send.assert_not_awaited()

    await alerts.alert_invoice_failed(None, provider='WATA', reason='timeout')
    send.assert_awaited_once()


async def test_success_resets_the_count(send):
    for _ in range(alerts.INVOICE_FAILURE_THRESHOLD - 1):
        await alerts.alert_invoice_failed(None, provider='WATA', reason='timeout')
    alerts.note_invoice_created('WATA')
    await alerts.alert_invoice_failed(None, provider='WATA', reason='timeout')

    send.assert_not_awaited()


async def test_old_failures_fall_out_of_the_window(send):
    with patch.object(alerts.time, 'monotonic', return_value=1000.0):
        for _ in range(alerts.INVOICE_FAILURE_THRESHOLD - 1):
            await alerts.alert_invoice_failed(None, provider='WATA', reason='timeout')
    with patch.object(alerts.time, 'monotonic', return_value=1000.0 + alerts.INVOICE_FAILURE_WINDOW_SECONDS + 1):
        await alerts.alert_invoice_failed(None, provider='WATA', reason='timeout')

    send.assert_not_awaited()


async def test_cooldown_stops_repeats_then_reminds(send):
    with patch.object(alerts.time, 'monotonic', return_value=1000.0):
        await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='x', blocked=True)
        await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='x', blocked=True)
    assert send.await_count == 1

    with patch.object(alerts.time, 'monotonic', return_value=1000.0 + alerts.INVOICE_ALERT_COOLDOWN_SECONDS + 1):
        await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='x', blocked=True)
    assert send.await_count == 2


async def test_block_is_not_silenced_by_a_recent_failure_alert(send):
    for _ in range(alerts.INVOICE_FAILURE_THRESHOLD):
        await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='timeout')
    await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='423 METHOD_BLOCKED', blocked=True)

    assert send.await_count == 2


async def test_providers_are_counted_separately(send):
    for provider in ('WATA', '2328.io', 'Platega'):
        await alerts.alert_invoice_failed(None, provider=provider, reason='timeout')

    send.assert_not_awaited()


async def test_telegram_failure_does_not_reach_the_client(send):
    send.side_effect = RuntimeError('telegram down')

    await alerts.alert_invoice_failed(None, provider='CryptoBot', reason='x', blocked=True)


class _BlockedCryptoBot:
    async def create_invoice(self, **kwargs: Any) -> None:
        kwargs['api_error'].update({'code': 423, 'name': 'METHOD_BLOCKED'})


class _SilentCryptoBot:
    async def create_invoice(self, **kwargs: Any) -> None:
        return None


def _payment_service(stub: Any) -> PaymentService:
    service = PaymentService.__new__(PaymentService)  # type: ignore[call-arg]
    service.bot = None
    service.cryptobot_service = stub
    return service


async def test_method_blocked_reaches_admins_from_real_payment(send):
    result = await _payment_service(_BlockedCryptoBot()).create_cryptobot_payment(None, 5, 3.0)

    assert result is None
    send.assert_awaited_once()
    assert '423 METHOD_BLOCKED' in send.await_args.args[1]


async def test_network_failure_of_cryptobot_waits_for_threshold(send):
    assert await _payment_service(_SilentCryptoBot()).create_cryptobot_payment(None, 5, 3.0) is None

    send.assert_not_awaited()
