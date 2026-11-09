"""xRocket: «Проверить статус» спрашивает xRocket и зачисляет оплату, если вебхук потерялся."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.database.models import (
    Base,
    PaymentMethod,
    Transaction,
    TransactionType,
    User,
    XRocketPayment,
)
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


def _mixin(remote_status: str = 'paid'):
    from app.services.payment.xrocket import XRocketPaymentMixin

    class Svc(XRocketPaymentMixin):
        def __init__(self):
            self.bot = None
            self.xrocket_service = SimpleNamespace(
                get_invoice=AsyncMock(
                    return_value={'id': 'inv-1', 'status': remote_status, 'paid': '2026-11-04T10:00:00Z'}
                )
            )

    return Svc()


async def _seed(db, *, status='active'):
    db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', balance_kopeks=0))
    db.add(
        XRocketPayment(
            id=42,
            user_id=1,
            invoice_id='inv-1',
            amount='5.5',
            asset='USDT',
            amount_kopeks=50000,
            status=status,
            payload='xrocket_topup_1_50000',
            created_at=datetime.now(UTC),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_status_check_credits_lost_webhook_once(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        svc = _mixin('paid')

        first = await svc.get_xrocket_payment_status(db, 42)
        second = await svc.get_xrocket_payment_status(db, 42)  # повторное нажатие

        assert first['payment'].is_paid
        assert second['payment'].is_paid
        user = await db.get(User, 1)
        await db.refresh(user)
        assert user.balance_kopeks == 50000
        deposits = (
            (await db.execute(select(Transaction).where(Transaction.type == TransactionType.DEPOSIT.value)))
            .scalars()
            .all()
        )
        assert [(t.amount_kopeks, t.external_id, t.payment_method) for t in deposits] == [
            (50000, 'inv-1', PaymentMethod.XROCKET.value)
        ]


@pytest.mark.asyncio
async def test_status_check_unpaid_invoice_changes_nothing(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        result = await _mixin('active').get_xrocket_payment_status(db, 42)
        assert result['payment'].status == 'active'
        user = await db.get(User, 1)
        await db.refresh(user)
        assert user.balance_kopeks == 0


def _callback(data: str):
    return SimpleNamespace(data=data, bot=None, answer=AsyncMock())


@pytest.mark.asyncio
async def test_status_button_queries_provider_for_pending_payment():
    from app.handlers.balance import xrocket as handler

    local = SimpleNamespace(
        user_id=1,
        invoice_id='inv-123456789',
        amount='5.5',
        asset='USDT',
        status='active',
        is_paid=False,
        is_pending=True,
        is_expired=False,
        created_at=datetime(2026, 11, 4, 10, 0, tzinfo=UTC),
    )
    paid = SimpleNamespace(**{**local.__dict__, 'status': 'paid', 'is_paid': True, 'is_pending': False})
    service = SimpleNamespace(get_xrocket_payment_status=AsyncMock(return_value={'payment': paid}))
    callback = _callback('check_xrocket_42')

    with (
        patch('app.database.crud.xrocket.get_xrocket_payment_by_id', AsyncMock(return_value=local)),
        patch.object(handler, 'PaymentService', lambda bot: service),
    ):
        await handler.check_xrocket_payment_status(callback, SimpleNamespace(id=1), db=object())

    service.get_xrocket_payment_status.assert_awaited_once()
    text = callback.answer.await_args.args[0]
    assert 'Оплачен' in text
    assert 'зачислены' in text


@pytest.mark.asyncio
async def test_status_button_does_not_query_provider_for_foreign_payment():
    from app.handlers.balance import xrocket as handler

    foreign = SimpleNamespace(user_id=2, is_paid=False)
    service = SimpleNamespace(get_xrocket_payment_status=AsyncMock())
    callback = _callback('check_xrocket_42')

    with (
        patch('app.database.crud.xrocket.get_xrocket_payment_by_id', AsyncMock(return_value=foreign)),
        patch.object(handler, 'PaymentService', lambda bot: service),
    ):
        await handler.check_xrocket_payment_status(callback, SimpleNamespace(id=1), db=object())

    service.get_xrocket_payment_status.assert_not_awaited()
    assert 'не найден' in callback.answer.await_args.args[0]


def test_xrocket_is_in_manual_and_auto_check_lists():
    from app.services import payment_verification_service as pvs

    assert PaymentMethod.XROCKET in pvs.SUPPORTED_MANUAL_CHECK_METHODS
    assert PaymentMethod.XROCKET in pvs.SUPPORTED_AUTO_CHECK_METHODS
    assert pvs.method_display_name(PaymentMethod.XROCKET) == 'xRocket'


@pytest.mark.asyncio
async def test_xrocket_client_has_request_timeout():
    import app.external.xrocket as module

    captured: dict = {}

    class _Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            raise RuntimeError('stop before network')

        async def __aexit__(self, *exc):
            return False

    service = module.XRocketService()
    service.api_token = 'token'
    with patch.object(module.aiohttp, 'ClientSession', _Session):
        assert await service.get_invoice('inv-1') is None

    timeout = captured.get('timeout')
    assert timeout is not None and 15 <= timeout.total <= 20


class _FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def json(self, content_type=None):
        import json as _json

        return _json.loads(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def request(self, method, url, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _client(monkeypatch, status: int, body: str):
    from app.external import xrocket as module

    monkeypatch.setattr(module.aiohttp, 'ClientSession', lambda **kwargs: _FakeSession(_FakeResponse(status, body)))
    service = module.XRocketService()
    service.api_token = 'token'
    return service


@pytest.mark.asyncio
async def test_deleted_invoice_is_reported_as_expired(monkeypatch):
    service = _client(monkeypatch, 404, '<html><body>Not Found</body></html>')
    assert await service.get_invoice(7375402) == {'id': 7375402, 'status': 'expired'}


@pytest.mark.asyncio
async def test_non_json_answer_is_not_an_exception(monkeypatch):
    service = _client(monkeypatch, 502, '<html>Bad Gateway</html>')
    assert await service.get_invoice(1) is None


@pytest.mark.asyncio
async def test_deleted_invoice_leaves_the_autocheck_queue(monkeypatch):
    from app.services.payment_verification_service import _is_xrocket_pending

    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        svc = _mixin('expired')
        svc.xrocket_service.get_invoice = AsyncMock(return_value={'id': 'inv-1', 'status': 'expired'})

        result = await svc.get_xrocket_payment_status(db, 42)

        assert result['payment'].status == 'expired'
        assert not _is_xrocket_pending(result['payment'])
        user = await db.get(User, 1)
        await db.refresh(user)
        assert user.balance_kopeks == 0
