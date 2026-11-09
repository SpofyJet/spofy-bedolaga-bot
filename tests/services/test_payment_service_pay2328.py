import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.database.crud import pay2328 as pay2328_crud
from app.services.payment_service import PaymentService


class StubPay2328Service:
    def __init__(
        self,
        response: dict[str, Any] | None,
        *,
        info_response: dict[str, Any] | None = None,
    ) -> None:
        self.response = response
        self.info_response = info_response
        self.calls: list[dict[str, Any]] = []
        self.info_calls: list[dict[str, str | None]] = []

    async def create_payment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.calls.append(payload)
        return self.response

    async def get_payment_info(
        self,
        *,
        uuid: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.info_calls.append({'uuid': uuid, 'order_id': order_id})
        return self.info_response


def _make_service(stub: StubPay2328Service | None) -> PaymentService:
    service = PaymentService.__new__(PaymentService)  # type: ignore[call-arg]
    service.bot = None
    service.pay2328_service = stub
    service.stars_service = None
    service.cryptobot_service = None
    service.wata_service = None
    return service


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


class DummySession:
    def __init__(self) -> None:
        self.added_objects: list[Any] = []

    async def commit(self) -> None:  # pragma: no cover - behaviour is mocked in tests
        return None

    async def refresh(self, obj: Any) -> None:  # pragma: no cover
        return None

    def add(self, obj: Any) -> None:  # pragma: no cover
        self.added_objects.append(obj)


class DummyLocalPayment:
    def __init__(self, payment_id: int = 123) -> None:
        self.id = payment_id
        self.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.mark.anyio('asyncio')
async def test_create_pay2328_payment_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        'state': 0,
        'result': {
            'uuid': 'pay2328-uuid',
            'order_id': 'order-123',
            'url': 'https://pay2328/pay',
            'payment_status': 'check',
            'payer_amount': '12.50',
            'payer_currency': 'USDT',
            'exchange_rate': '0.0125',
            'expires_at': '2026-01-11T21:00:00Z',
        },
    }
    stub = StubPay2328Service(response)
    service = _make_service(stub)
    db = DummySession()
    monkeypatch.setattr(settings, 'PAY2328_CALLBACK_URL', 'https://hooks.example/pay2328-webhook')
    monkeypatch.setattr(settings, 'PAY2328_MARKUP_PERCENT', 3.0)

    captured_args: dict[str, Any] = {}

    async def fake_create_pay2328_payment(**kwargs: Any) -> DummyLocalPayment:
        captured_args.update(kwargs)
        return DummyLocalPayment(payment_id=555)

    monkeypatch.setattr(
        pay2328_crud,
        'create_pay2328_payment',
        fake_create_pay2328_payment,
        raising=False,
    )

    result = await service.create_pay2328_payment(
        db=db,
        user_id=42,
        amount_kopeks=15000,
        description='Пополнение',
        language='ru',
    )

    assert result is not None
    assert result['local_payment_id'] == 555
    assert result['uuid'] == 'pay2328-uuid'
    assert result['order_id'] == 'order-123'
    assert result['payment_url'] == 'https://pay2328/pay'
    sent = stub.calls[0]
    assert sent['amount'] == '150.00'
    assert sent['currency'] == 'RUB'
    assert sent['url_callback'] == 'https://hooks.example/pay2328-webhook'
    assert sent['price_markup'] == 3
    assert 'ttl_seconds' in sent
    assert captured_args['expires_at'] == datetime(2026, 1, 11, 21, 0, tzinfo=UTC)
    assert captured_args['uuid'] == 'pay2328-uuid'
    assert captured_args['user_id'] == 42


@pytest.mark.anyio('asyncio')
async def test_create_pay2328_payment_returns_none_without_service() -> None:
    service = _make_service(None)
    db = DummySession()

    result = await service.create_pay2328_payment(
        db=db,
        user_id=1,
        amount_kopeks=10000,
        description='Пополнение',
    )

    assert result is None


@pytest.mark.anyio('asyncio')
async def test_create_pay2328_payment_handles_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubPay2328Service(response=None)
    service = _make_service(stub)
    db = DummySession()

    called = False

    async def fake_create_pay2328_payment(**kwargs: Any) -> DummyLocalPayment:
        nonlocal called
        called = True
        return DummyLocalPayment()

    monkeypatch.setattr(
        pay2328_crud,
        'create_pay2328_payment',
        fake_create_pay2328_payment,
        raising=False,
    )

    result = await service.create_pay2328_payment(
        db=db,
        user_id=1,
        amount_kopeks=20000,
        description='Пополнение',
    )

    assert result is None
    assert called is False


@pytest.mark.anyio('asyncio')
async def test_sync_pay2328_payment_status_success(monkeypatch: pytest.MonkeyPatch) -> None:
    info_response = {
        'state': 0,
        'result': {
            'uuid': 'pay2328-uuid',
            'order_id': 'order-123',
            'status': 'paid',
            'payment_amount': '100.00',
        },
    }
    stub = StubPay2328Service(response=None, info_response=info_response)
    service = _make_service(stub)
    db = DummySession()

    payment = SimpleNamespace(
        id=55,
        uuid='pay2328-uuid',
        order_id='order-123',
        status='check',
        user_id=7,
    )

    async def fake_get_by_id(db, payment_id):
        assert payment_id == payment.id
        return payment

    captured: dict[str, Any] = {}

    async def fake_process(self, db, payload, *, metadata_key):
        captured['payload'] = payload
        captured['metadata_key'] = metadata_key
        return SimpleNamespace(transaction_id=999, **payload)

    monkeypatch.setattr(pay2328_crud, 'get_pay2328_payment_by_id', fake_get_by_id, raising=False)
    monkeypatch.setattr(PaymentService, '_process_pay2328_payload', fake_process, raising=False)

    result = await service.sync_pay2328_payment_status(db, local_payment_id=payment.id)

    assert result is not None
    assert result.transaction_id == 999
    assert captured['metadata_key'] == 'last_status_check'
    assert captured['payload']['uuid'] == payment.uuid
    assert stub.info_calls == [{'uuid': payment.uuid, 'order_id': payment.order_id}]


@pytest.mark.anyio('asyncio')
async def test_sync_pay2328_payment_status_without_response(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubPay2328Service(response=None, info_response=None)
    service = _make_service(stub)
    db = DummySession()

    payment = SimpleNamespace(
        id=12,
        uuid='pay2328-uuid',
        order_id='order-123',
        status='check',
        user_id=5,
    )

    async def fake_get_by_id(db, payment_id):
        assert payment_id == payment.id
        return payment

    async def fake_process(*args, **kwargs):  # pragma: no cover - ensure not called
        raise AssertionError('_process_pay2328_payload should not be called')

    monkeypatch.setattr(pay2328_crud, 'get_pay2328_payment_by_id', fake_get_by_id, raising=False)
    monkeypatch.setattr(PaymentService, '_process_pay2328_payload', fake_process, raising=False)

    result = await service.sync_pay2328_payment_status(db, local_payment_id=payment.id)

    assert result is payment
    assert stub.info_calls == [{'uuid': payment.uuid, 'order_id': payment.order_id}]


def _stored_payment(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        'id': 1,
        'uuid': 'pay2328-uuid',
        'order_id': 'order-1',
        'status': 'check',
        'transaction_id': None,
        'user_id': 8,
        'amount_float': 150.0,
        'amount_kopeks': 15000,
        'metadata_json': {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_crud(monkeypatch: pytest.MonkeyPatch, payment: SimpleNamespace) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []

    async def by_uuid(db: Any, uuid: str) -> SimpleNamespace:
        return payment

    async def update(db: Any, uuid: str, **kwargs: Any) -> SimpleNamespace:
        updates.append(kwargs)
        return payment

    monkeypatch.setattr(pay2328_crud, 'get_pay2328_payment_by_uuid', by_uuid)
    monkeypatch.setattr(pay2328_crud, 'update_pay2328_payment', update)
    monkeypatch.setattr(pay2328_crud, 'get_pay2328_payment_by_id_for_update', lambda db, pid: _ready(payment))
    return updates


async def _ready(value: Any) -> Any:
    return value


@pytest.mark.anyio('asyncio')
async def test_replayed_webhook_does_not_touch_credited_payment(monkeypatch: pytest.MonkeyPatch) -> None:
    payment = _stored_payment(status='paid', transaction_id=77)
    updates = _patch_crud(monkeypatch, payment)
    service = _make_service(StubPay2328Service(None))

    assert await service.process_pay2328_webhook(DummySession(), {'uuid': payment.uuid, 'payment_status': 'check'})
    assert updates == []


@pytest.mark.anyio('asyncio')
async def test_refund_status_is_recorded_without_second_credit(monkeypatch: pytest.MonkeyPatch) -> None:
    payment = _stored_payment(status='paid', transaction_id=77)
    updates = _patch_crud(monkeypatch, payment)
    service = _make_service(StubPay2328Service(None))

    assert await service.process_pay2328_webhook(
        DummySession(), {'uuid': payment.uuid, 'payment_status': 'refund_process'}
    )
    assert updates[0]['status'] == 'refund_process'


@pytest.mark.anyio('asyncio')
@pytest.mark.parametrize('status', ['underpaid', 'aml_lock', 'cancel', 'awaiting_confirmation'])
async def test_non_paid_statuses_never_credit(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    payment = _stored_payment()
    _patch_crud(monkeypatch, payment)

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError('баланс не должен зачисляться')

    monkeypatch.setattr('app.services.payment_service.create_transaction', forbidden)
    service = _make_service(StubPay2328Service(None))

    assert await service.process_pay2328_webhook(DummySession(), {'uuid': payment.uuid, 'payment_status': status})
