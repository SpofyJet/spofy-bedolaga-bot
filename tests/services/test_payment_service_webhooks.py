"""Интеграционные проверки обработки вебхуков PaymentService."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.services.payment.cryptobot as cryptobot_module
from app.config import settings
from app.database.models import PaymentMethod
from app.services.payment_service import PaymentService


def _make_service(bot: DummyBot) -> PaymentService:
    service = PaymentService.__new__(PaymentService)  # type: ignore[call-arg]
    service.bot = bot
    service.stars_service = None
    service.cryptobot_service = None
    service.heleket_service = None
    return service


class DummyBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(
        self, *args: Any, **kwargs: Any
    ) -> None:  # pragma: no cover - бизнес-логика тестируется через вызов
        self.sent_messages.append({'args': args, 'kwargs': kwargs})


class FakeScalarResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)

    def all(self) -> list[Any]:  # pragma: no cover - утилитарный метод
        return list(self._items)

    def first(self) -> Any:  # pragma: no cover - утилитарный метод
        return self._items[0] if self._items else None

    def one(self) -> Any:  # pragma: no cover - утилитарный метод
        if len(self._items) != 1:
            raise ValueError('Expected exactly one result')
        return self._items[0]

    def one_or_none(self) -> Any:  # pragma: no cover - утилитарный метод
        if not self._items:
            return None
        if len(self._items) > 1:
            raise ValueError('Expected zero or one result')
        return self._items[0]

    def __iter__(self):  # pragma: no cover - утилитарный метод
        return iter(self._items)


class FakeResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def _as_iterable(self) -> list[Any]:
        if isinstance(self._value, list):
            return self._value
        if self._value is None:
            return []
        return [self._value]

    def scalar(self) -> Any:
        items = self._as_iterable()
        return items[0] if items else None

    def scalar_one_or_none(self) -> Any:
        items = self._as_iterable()
        if not items:
            return None
        if len(items) > 1:
            raise ValueError('Expected zero or one result')
        return items[0]

    def scalar_one(self) -> Any:
        items = self._as_iterable()
        if len(items) != 1:
            raise ValueError('Expected exactly one result')
        return items[0]

    def first(self) -> Any:  # pragma: no cover - утилитарный метод
        items = self._as_iterable()
        return items[0] if items else None

    def all(self) -> list[Any]:  # pragma: no cover - утилитарный метод
        return list(self._as_iterable())

    def one_or_none(self) -> Any:  # pragma: no cover - утилитарный метод
        items = self._as_iterable()
        if not items:
            return None
        if len(items) > 1:
            raise ValueError('Expected zero or one result')
        return items[0]

    def scalars(self) -> FakeScalarResult:  # pragma: no cover - утилитарный метод
        return FakeScalarResult(self._as_iterable())


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.refreshed: list[Any] = []
        self.added: list[Any] = []
        self.execute_statements: list[Any] = []
        self.execute_results: list[Any] = []
        # Optional opt-in routing: maps an entity-class-name substring to the
        # object a matching `select(Entity)...` statement should resolve to.
        # Lets ORM-level lock/select calls (e.g. YooKassaPayment FOR UPDATE,
        # User eager-load) return the right test object regardless of call order.
        self.route_by_entity: dict[str, Any] | None = None

    def _route(self, statement: Any) -> Any | None:
        if not self.route_by_entity:
            return None
        try:
            descriptions = statement.column_descriptions
        except Exception:
            return None
        for description in descriptions:
            entity = description.get('entity')
            entity_name = getattr(entity, '__name__', '')
            for key, value in self.route_by_entity.items():
                if key in entity_name:
                    return value
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None

    async def rollback(self) -> None:  # pragma: no cover
        return None

    async def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)

    def add(self, obj: Any) -> None:  # pragma: no cover - используется при создании транзакций
        self.added.append(obj)

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeResult:
        self.execute_statements.append(statement)
        routed = self._route(statement)
        if routed is not None:
            return routed if isinstance(routed, FakeResult) else FakeResult(routed)
        if self.execute_results:
            result = self.execute_results.pop(0)
            if callable(result):  # pragma: no cover - гибкость для будущих тестов
                result = result(statement, *args, **kwargs)
        else:
            result = None

        if isinstance(result, FakeResult):
            return result

        return FakeResult(result)


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


@pytest.mark.anyio('asyncio')
async def test_process_cryptobot_webhook_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = DummyBot()
    service = _make_service(bot)
    fake_session = FakeSession()
    payment = SimpleNamespace(
        invoice_id='inv_1',
        user_id=7,
        status='pending',
        transaction_id=None,
        amount='12.50',
        asset='USDT',
        amount_float=12.5,
    )

    async def fake_get_crypto(db, invoice_id):
        return payment

    async def fake_update_status(db, invoice_id, status, paid_at):
        payment.status = status
        payment.paid_at = paid_at
        return payment

    async def fake_link(db, invoice_id, transaction_id):
        payment.transaction_id = transaction_id

    fake_cryptobot_module = ModuleType('app.database.crud.cryptobot')
    fake_cryptobot_module.get_cryptobot_payment_by_invoice_id = fake_get_crypto
    fake_cryptobot_module.get_cryptobot_payment_by_invoice_id_for_update = fake_get_crypto
    fake_cryptobot_module.update_cryptobot_payment_status = fake_update_status
    fake_cryptobot_module.link_cryptobot_payment_to_transaction = fake_link
    monkeypatch.setitem(sys.modules, 'app.database.crud.cryptobot', fake_cryptobot_module)

    transactions: list[dict[str, Any]] = []
    created_transaction: SimpleNamespace | None = None

    async def fake_create_transaction(db, **kwargs):
        nonlocal created_transaction
        transactions.append(kwargs)
        created_transaction = SimpleNamespace(id=888, **kwargs)
        return created_transaction

    fake_transaction_module = ModuleType('app.database.crud.transaction')
    fake_transaction_module.create_transaction = fake_create_transaction

    async def fake_get_transaction_by_id(db, transaction_id):
        return created_transaction

    fake_transaction_module.get_transaction_by_id = fake_get_transaction_by_id

    async def fake_emit_side_effects(db, transaction, **kwargs):
        return None

    fake_transaction_module.emit_transaction_side_effects = fake_emit_side_effects
    monkeypatch.setitem(sys.modules, 'app.database.crud.transaction', fake_transaction_module)
    monkeypatch.setattr('app.services.payment_service.create_transaction', fake_create_transaction)

    user = SimpleNamespace(
        id=7,
        telegram_id=700,
        balance_kopeks=0,
        has_made_first_topup=False,
        promo_group=None,
        subscription=None,
        referred_by_id=None,
        referrer=None,
    )
    user.get_primary_promo_group = lambda: getattr(user, 'promo_group', None)

    async def fake_get_user_crypto(db, user_id):
        return user

    monkeypatch.setattr('app.services.payment_service.get_user_by_id', fake_get_user_crypto)

    async def fake_lock_user(db, user):
        return user

    fake_user_module = ModuleType('app.database.crud.user')
    fake_user_module.get_user_by_id = fake_get_user_crypto
    fake_user_module.lock_user_for_update = fake_lock_user
    monkeypatch.setitem(sys.modules, 'app.database.crud.user', fake_user_module)

    referral_crypto = SimpleNamespace(process_referral_topup=AsyncMock())
    monkeypatch.setitem(sys.modules, 'app.services.referral_service', referral_crypto)

    admin_calls: list[Any] = []

    class DummyAdminService2:
        def __init__(self, bot):
            self.bot = bot

        async def send_balance_topup_notification(self, *args, **kwargs):
            admin_calls.append((args, kwargs))

    monkeypatch.setitem(
        sys.modules,
        'app.services.admin_notification_service',
        SimpleNamespace(AdminNotificationService=DummyAdminService2),
    )

    class DummyAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def rollback(self):  # pragma: no cover - defensive stub
            return None

    monkeypatch.setattr(cryptobot_module, 'AsyncSessionLocal', DummyAsyncSession)
    monkeypatch.setattr('app.services.payment_service.currency_converter.usd_to_rub', AsyncMock(return_value=140.0))
    monkeypatch.setattr(type(settings), 'format_price', lambda self, amount: f'{amount / 100:.2f}₽', raising=False)
    service.build_topup_success_keyboard = AsyncMock(return_value=None)

    payload = {
        'update_type': 'invoice_paid',
        'payload': {
            'invoice_id': 'inv_1',
            'paid_at': '2024-01-01T12:00:00Z',
        },
    }

    result = await service.process_cryptobot_webhook(fake_session, payload)

    assert result is True
    assert transactions and transactions[0]['amount_kopeks'] == 14000
    assert user.balance_kopeks == 14000
    assert payment.transaction_id == 888
    assert bot.sent_messages
    assert admin_calls


@pytest.mark.anyio('asyncio')
async def test_process_heleket_webhook_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = DummyBot()
    service = _make_service(bot)
    fake_session = FakeSession()

    payment = SimpleNamespace(
        id=5001,
        uuid='heleket-uuid',
        order_id='heleket-order',
        user_id=77,
        amount='150.00',
        amount_float=150.0,
        amount_kopeks=15000,
        status='check',
        payer_amount=None,
        payer_currency=None,
        exchange_rate=None,
        discount_percent=None,
        payment_url=None,
        transaction_id=None,
    )

    async def fake_get_by_uuid(db, uuid):
        return payment if uuid == payment.uuid else None

    async def fake_get_by_order(db, order_id):
        return payment if order_id == payment.order_id else None

    async def fake_update(
        db,
        uuid,
        *,
        status=None,
        payer_amount=None,
        payer_currency=None,
        exchange_rate=None,
        discount_percent=None,
        paid_at=None,
        payment_url=None,
        metadata=None,
    ):
        if status is not None:
            payment.status = status
        if payer_amount is not None:
            payment.payer_amount = payer_amount
        if payer_currency is not None:
            payment.payer_currency = payer_currency
        if exchange_rate is not None:
            payment.exchange_rate = exchange_rate
        if discount_percent is not None:
            payment.discount_percent = discount_percent
        if payment_url is not None:
            payment.payment_url = payment_url
        payment.paid_at = paid_at
        if metadata:
            payment.metadata_json = metadata
        return payment

    async def fake_link(db, uuid, transaction_id):
        payment.transaction_id = transaction_id
        return payment

    async def fake_get_by_id_for_update(db, payment_id):
        return payment if payment_id == payment.id else None

    heleket_module = ModuleType('app.database.crud.heleket')
    heleket_module.get_heleket_payment_by_uuid = fake_get_by_uuid
    heleket_module.get_heleket_payment_by_order_id = fake_get_by_order
    heleket_module.get_heleket_payment_by_id_for_update = fake_get_by_id_for_update
    heleket_module.update_heleket_payment = fake_update
    heleket_module.link_heleket_payment_to_transaction = fake_link
    monkeypatch.setitem(sys.modules, 'app.database.crud.heleket', heleket_module)

    transactions: list[dict[str, Any]] = []

    async def fake_create_transaction(db, **kwargs):
        transactions.append(kwargs)
        return SimpleNamespace(id=321, **kwargs)

    monkeypatch.setattr('app.services.payment_service.create_transaction', fake_create_transaction)

    user = SimpleNamespace(
        id=77,
        telegram_id=7700,
        balance_kopeks=0,
        has_made_first_topup=False,
        promo_group=None,
        subscription=None,
        referred_by_id=None,
        referrer=None,
        language='ru',
    )
    user.get_primary_promo_group = lambda: getattr(user, 'promo_group', None)

    async def fake_get_user(db, user_id):
        return user if user_id == user.id else None

    monkeypatch.setattr('app.services.payment_service.get_user_by_id', fake_get_user)
    monkeypatch.setattr('app.services.payment.heleket.format_referrer_info', lambda u: '')

    monkeypatch.setattr('app.database.crud.user.lock_user_for_update', AsyncMock(side_effect=lambda db, u: u))
    monkeypatch.setattr('app.database.crud.transaction.emit_transaction_side_effects', AsyncMock())

    monkeypatch.setattr(type(settings), 'format_price', lambda self, amount: f'{amount / 100:.2f}₽', raising=False)

    referral_stub = SimpleNamespace(process_referral_topup=AsyncMock())
    monkeypatch.setitem(sys.modules, 'app.services.referral_service', referral_stub)

    admin_calls: list[Any] = []

    class DummyAdminService:
        def __init__(self, bot):
            self.bot = bot

        async def send_balance_topup_notification(self, *args, **kwargs):
            admin_calls.append((args, kwargs))

    monkeypatch.setitem(
        sys.modules,
        'app.services.admin_notification_service',
        SimpleNamespace(AdminNotificationService=DummyAdminService),
    )

    service.build_topup_success_keyboard = AsyncMock(return_value=None)

    payload = {
        'uuid': 'heleket-uuid',
        'status': 'paid',
        'payer_amount': '2.50',
        'payer_currency': 'USDT',
        'discount_percent': -5,
        'payer_amount_exchange_rate': '0.0166',
        'paid_at': '2024-01-02T12:00:00Z',
        'url': 'https://pay.example',
    }

    result = await service.process_heleket_webhook(fake_session, payload)

    assert result is True
    assert transactions and transactions[0]['payment_method'] == PaymentMethod.HELEKET
    assert payment.transaction_id == 321
    assert user.balance_kopeks == 15000
    assert user.has_made_first_topup is True
    assert fake_session.commits >= 1
    assert bot.sent_messages
    assert admin_calls
    referral_stub.process_referral_topup.assert_awaited_once()
