import os
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

BACKUP_DIR = ROOT_DIR / 'data' / 'backups'
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault('BOT_TOKEN', 'test-token')

from app.config import settings
from app.database.models import PaymentMethod
from app.services.payment.cryptobot import CryptoBotPaymentMixin
from app.services.pricing_engine import PricingEngine, pricing_engine
from app.services.subscription_renewal_service import (
    SubscriptionRenewalPricing,
    SubscriptionRenewalResult,
    build_payment_descriptor,
    decode_payment_payload,
    encode_payment_payload,
)
from app.webapi.routes import miniapp
from app.webapi.schemas.miniapp import (
    MiniAppPaymentCreateRequest,
    MiniAppPaymentIntegrationType,
    MiniAppPaymentMethodsRequest,
    MiniAppPaymentStatusQuery,
)


@pytest.fixture(autouse=True)
def _clear_pricing_engine_instance_leak():
    """Защита от перекрёстного загрязнения синглтона pricing_engine между тестами.

    Другие тест-модули (например, авто-продление) патчат
    ``pricing_engine.calculate_renewal_price`` на ЭКЗЕМПЛЯРЕ-синглтоне. pytest
    monkeypatch при откате восстанавливает унаследованный метод через setattr,
    а НЕ delattr — и на синглтоне остаётся «висящий» атрибут экземпляра, который
    перекрывает патч на УРОВНЕ КЛАССА, на который опираются тесты продления здесь.
    Снимаем его перед каждым тестом, чтобы эндпоинт продления вызвал мок класса.
    """
    pricing_engine.__dict__.pop('calculate_renewal_price', None)
    yield


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_compute_cryptobot_limits_scale_with_rate():
    low_rate_min, low_rate_max = miniapp._compute_cryptobot_limits(70.0)
    high_rate_min, high_rate_max = miniapp._compute_cryptobot_limits(120.0)

    assert low_rate_min == 7000
    assert low_rate_max == 7000000
    assert high_rate_min == 12000
    assert high_rate_max == 12000000
    assert high_rate_min > low_rate_min
    assert high_rate_max > low_rate_max


def test_encode_decode_renewal_payload_preserves_snapshot():
    pricing_model = SubscriptionRenewalPricing(
        period_days=30,
        period_id='days:30',
        months=1,
        base_original_total=12000,
        discounted_total=10000,
        final_total=9000,
        promo_discount_value=1000,
        promo_discount_percent=10,
        overall_discount_percent=25,
        per_month=9000,
        server_ids=[1, 2],
        details={'servers_price_per_month': 1000},
    )

    descriptor = build_payment_descriptor(
        user_id=1,
        subscription_id=42,
        period_days=30,
        total_amount_kopeks=pricing_model.final_total,
        missing_amount_kopeks=1000,
        pricing_snapshot=pricing_model.to_payload(),
    )

    payload_value = encode_payment_payload(descriptor)
    decoded = decode_payment_payload(payload_value, expected_user_id=1)

    assert decoded is not None
    assert decoded.total_amount_kopeks == 9000
    assert decoded.missing_amount_kopeks == 1000
    assert decoded.pricing_snapshot is not None
    assert decoded.pricing_snapshot.get('server_ids') == [1, 2]


@pytest.mark.anyio('asyncio')
async def test_cryptobot_renewal_uses_pricing_snapshot(monkeypatch):
    module = sys.modules['app.services.payment.cryptobot']
    mixin = CryptoBotPaymentMixin()

    subscription = types.SimpleNamespace(
        id=77, connected_squads=[], traffic_limit_gb=100, device_limit=5, tariff=None, tariff_id=None
    )
    user = types.SimpleNamespace(id=5, balance_kopeks=7000, subscription=subscription)

    pricing_model = SubscriptionRenewalPricing(
        period_days=30,
        period_id='days:30',
        months=1,
        base_original_total=12000,
        discounted_total=10000,
        final_total=10000,
        promo_discount_value=0,
        promo_discount_percent=0,
        overall_discount_percent=0,
        per_month=10000,
        server_ids=[11, 22],
        details={'servers_individual_prices': [500, 500]},
    )

    descriptor = build_payment_descriptor(
        user_id=5,
        subscription_id=77,
        period_days=30,
        total_amount_kopeks=10000,
        missing_amount_kopeks=3000,
        pricing_snapshot=pricing_model.to_payload(),
    )

    payment = types.SimpleNamespace(invoice_id='INV-1', user_id=5)

    async def fake_get_user_by_id(db, user_id):
        return user if user_id == 5 else None

    monkeypatch.setitem(
        sys.modules, 'app.services.payment_service', types.SimpleNamespace(get_user_by_id=fake_get_user_by_id)
    )

    async def fail_calculate(*args, **kwargs):
        raise AssertionError('PricingEngine.calculate_renewal_price should not be called when snapshot is present')

    monkeypatch.setattr(PricingEngine, 'calculate_renewal_price', fail_calculate)

    captured: dict[str, Any] = {}

    async def fake_finalize(db, u, sub, pricing, *, charge_balance_amount=None, description=None, payment_method=None):
        captured['pricing'] = pricing
        captured['charge'] = charge_balance_amount
        captured['description'] = description
        captured['payment_method'] = payment_method
        return SubscriptionRenewalResult(
            subscription=types.SimpleNamespace(id=sub.id, end_date=datetime.now(UTC)),
            transaction=types.SimpleNamespace(id=999),
            total_amount_kopeks=pricing.final_total,
            charged_from_balance_kopeks=charge_balance_amount or pricing.final_total,
            old_end_date=None,
        )

    monkeypatch.setattr(module.renewal_service, 'finalize', fake_finalize)

    async def fake_link(db, invoice_id, transaction_id):
        captured['linked'] = (invoice_id, transaction_id)

    cryptobot_crud = types.SimpleNamespace(link_cryptobot_payment_to_transaction=fake_link)

    async def fake_get_subscription_by_id_for_user(db, subscription_id, user_id):
        return subscription if subscription_id == 77 and user_id == 5 else None

    monkeypatch.setattr(
        'app.database.crud.subscription.get_subscription_by_id_for_user',
        fake_get_subscription_by_id_for_user,
    )

    result = await mixin._process_subscription_renewal_payment(
        db=types.SimpleNamespace(),
        payment=payment,
        descriptor=descriptor,
        cryptobot_crud=cryptobot_crud,
    )

    assert result is True
    assert captured['pricing'].server_ids == [11, 22]
    assert captured['pricing'].final_total == 10000
    assert captured['charge'] == 7000
    assert captured['payment_method'] == PaymentMethod.CRYPTOBOT
    assert captured['linked'] == ('INV-1', 999)


@pytest.mark.anyio('asyncio')
async def test_cryptobot_renewal_accepts_changed_pricing_without_snapshot(monkeypatch):
    module = sys.modules['app.services.payment.cryptobot']
    mixin = CryptoBotPaymentMixin()

    subscription = types.SimpleNamespace(
        id=55, connected_squads=[], traffic_limit_gb=50, device_limit=3, tariff=None, tariff_id=None
    )
    user = types.SimpleNamespace(id=8, balance_kopeks=4000, subscription=subscription)

    descriptor = build_payment_descriptor(
        user_id=8,
        subscription_id=55,
        period_days=30,
        total_amount_kopeks=5000,
        missing_amount_kopeks=1000,
    )

    payment = types.SimpleNamespace(invoice_id='INV-2', user_id=8)

    async def fake_get_user_by_id(db, user_id):
        return user if user_id == 8 else None

    monkeypatch.setitem(
        sys.modules, 'app.services.payment_service', types.SimpleNamespace(get_user_by_id=fake_get_user_by_id)
    )

    # Recalculated price is LOWER than descriptor — user benefits, should proceed
    recalculated_pricing = SubscriptionRenewalPricing(
        period_days=30,
        period_id='days:30',
        months=1,
        base_original_total=4800,
        discounted_total=4800,
        final_total=4800,
        promo_discount_value=0,
        promo_discount_percent=0,
        overall_discount_percent=0,
        per_month=4800,
        server_ids=[],
        details={},
    )

    async def fake_calculate(self, db, sub, period_days, *, user=None):
        return recalculated_pricing

    monkeypatch.setattr(PricingEngine, 'calculate_renewal_price', fake_calculate)

    captured: dict[str, Any] = {}

    async def fake_finalize(db, u, sub, pricing, *, charge_balance_amount=None, description=None, payment_method=None):
        captured['pricing'] = pricing
        captured['charge'] = charge_balance_amount
        return SubscriptionRenewalResult(
            subscription=types.SimpleNamespace(id=sub.id, end_date=datetime.now(UTC)),
            transaction=None,
            total_amount_kopeks=pricing.final_total,
            charged_from_balance_kopeks=charge_balance_amount or pricing.final_total,
            old_end_date=None,
        )

    monkeypatch.setattr(module.renewal_service, 'finalize', fake_finalize)

    async def noop_link(*args, **kwargs):
        return None

    cryptobot_crud = types.SimpleNamespace(link_cryptobot_payment_to_transaction=noop_link)

    async def fake_get_subscription_by_id_for_user(db, subscription_id, user_id):
        return subscription if subscription_id == 55 and user_id == 8 else None

    monkeypatch.setattr(
        'app.database.crud.subscription.get_subscription_by_id_for_user',
        fake_get_subscription_by_id_for_user,
    )

    result = await mixin._process_subscription_renewal_payment(
        db=types.SimpleNamespace(),
        payment=payment,
        descriptor=descriptor,
        cryptobot_crud=cryptobot_crud,
    )

    assert result is True
    # With C-4 fix: recalculated price (4800) < descriptor (5000) → use recalculated
    assert captured['pricing'].final_total == 4800
    # M-5 fix: required_balance = max(0, final_total - missing) = max(0, 4800 - 1000) = 3800
    assert captured['charge'] == 3800


@pytest.mark.anyio('asyncio')
async def test_cryptobot_webhook_uses_inline_payload_when_db_missing(monkeypatch):
    module = sys.modules['app.services.payment.cryptobot']
    mixin = CryptoBotPaymentMixin()

    subscription = types.SimpleNamespace(
        id=91, connected_squads=[], traffic_limit_gb=80, device_limit=4, tariff=None, tariff_id=None
    )
    user = types.SimpleNamespace(id=21, balance_kopeks=6000, subscription=subscription)

    pricing_model = SubscriptionRenewalPricing(
        period_days=30,
        period_id='days:30',
        months=1,
        base_original_total=9000,
        discounted_total=9000,
        final_total=9000,
        promo_discount_value=0,
        promo_discount_percent=0,
        overall_discount_percent=0,
        per_month=9000,
        server_ids=[5, 6],
        details={'servers_individual_prices': [300, 300]},
    )

    descriptor = build_payment_descriptor(
        user_id=21,
        subscription_id=91,
        period_days=30,
        total_amount_kopeks=9000,
        missing_amount_kopeks=3000,
        pricing_snapshot=pricing_model.to_payload(),
    )

    encoded_payload = encode_payment_payload(descriptor)

    payment = types.SimpleNamespace(
        invoice_id='INV-webhook',
        user_id=21,
        status='active',
        payload=None,
        amount='90.00',
        asset='USDT',
        bot_invoice_url=None,
        mini_app_invoice_url=None,
        web_app_invoice_url=None,
        description='Продление подписки',
    )

    async def fake_get_user_by_id(db, user_id):
        return user if user_id == 21 else None

    monkeypatch.setitem(
        sys.modules,
        'app.services.payment_service',
        types.SimpleNamespace(get_user_by_id=fake_get_user_by_id),
    )

    async def fail_calculate(*args, **kwargs):
        raise AssertionError('PricingEngine.calculate_renewal_price should not be called')

    monkeypatch.setattr(PricingEngine, 'calculate_renewal_price', fail_calculate)

    captured: dict[str, Any] = {}

    async def fake_finalize(db, u, sub, pricing, *, charge_balance_amount=None, description=None, payment_method=None):
        captured['pricing'] = pricing
        captured['charge'] = charge_balance_amount
        captured['description'] = description
        captured['payment_method'] = payment_method
        return SubscriptionRenewalResult(
            subscription=types.SimpleNamespace(id=sub.id, end_date=datetime.now(UTC)),
            transaction=types.SimpleNamespace(id=1234),
            total_amount_kopeks=pricing.final_total,
            charged_from_balance_kopeks=charge_balance_amount or pricing.final_total,
            old_end_date=None,
        )

    monkeypatch.setattr(module.renewal_service, 'finalize', fake_finalize)

    linked: dict[str, Any] = {}

    async def fake_get(db, invoice_id):
        return payment if invoice_id == payment.invoice_id else None

    async def fake_update(db, invoice_id, status, paid_at):
        if invoice_id == payment.invoice_id:
            payment.status = status
            payment.paid_at = paid_at
        return payment

    async def fake_link(db, invoice_id, transaction_id):
        linked['value'] = (invoice_id, transaction_id)
        return payment

    monkeypatch.setitem(
        sys.modules,
        'app.database.crud.cryptobot',
        types.SimpleNamespace(
            get_cryptobot_payment_by_invoice_id=fake_get,
            get_cryptobot_payment_by_invoice_id_for_update=fake_get,
            update_cryptobot_payment_status=fake_update,
            link_cryptobot_payment_to_transaction=fake_link,
        ),
    )

    async def fake_get_subscription_by_id_for_user(db, subscription_id, user_id):
        return subscription if subscription_id == 91 and user_id == 21 else None

    monkeypatch.setattr(
        'app.database.crud.subscription.get_subscription_by_id_for_user',
        fake_get_subscription_by_id_for_user,
    )

    class DummyDb:
        async def flush(self):
            return None

        async def commit(self):
            return None

    webhook_payload = {
        'update_type': 'invoice_paid',
        'payload': {
            'invoice_id': payment.invoice_id,
            'paid_at': '2024-05-01T12:00:00Z',
            'payload': encoded_payload,
        },
    }

    result = await mixin.process_cryptobot_webhook(DummyDb(), webhook_payload)

    assert result is True
    assert captured['pricing'].final_total == 9000
    assert captured['charge'] == 6000
    assert captured['payment_method'] == PaymentMethod.CRYPTOBOT
    assert linked['value'] == (payment.invoice_id, 1234)


@pytest.mark.anyio('asyncio')
async def test_create_payment_link_wata_returns_payload(monkeypatch):
    monkeypatch.setattr(settings, 'WATA_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'WATA_ACCESS_TOKEN', 'token', raising=False)
    monkeypatch.setattr(settings, 'WATA_TERMINAL_PUBLIC_ID', 'terminal', raising=False)
    monkeypatch.setattr(settings, 'WATA_MIN_AMOUNT_KOPEKS', 1000, raising=False)
    monkeypatch.setattr(settings, 'WATA_MAX_AMOUNT_KOPEKS', 5000000, raising=False)

    captured_call: dict[str, Any] = {}

    class DummyPaymentService:
        def __init__(self, *args, **kwargs):
            pass

        async def create_wata_payment(self, db, **kwargs):
            captured_call.update({'db': db, **kwargs})
            return {
                'local_payment_id': 202,
                'payment_link_id': 'link_202',
                'payment_url': 'https://wata.example/pay',
                'status': 'Opened',
                'order_id': 'order_202',
            }

    async def fake_resolve_user(db, init_data):
        return types.SimpleNamespace(id=555, telegram_id=555, language='ru'), {}

    monkeypatch.setattr(miniapp, 'PaymentService', lambda *args, **kwargs: DummyPaymentService())
    monkeypatch.setattr(miniapp, '_resolve_user_from_init_data', fake_resolve_user)

    payload = MiniAppPaymentCreateRequest(
        initData='init',
        method='wata',
        amountKopeks=25000,
    )

    response = await miniapp.create_payment_link(payload, db=types.SimpleNamespace())

    assert response.payment_url == 'https://wata.example/pay'
    assert response.amount_kopeks == 25000
    assert response.extra['local_payment_id'] == 202
    assert response.extra['payment_link_id'] == 'link_202'
    assert response.extra['payment_id'] == 'link_202'
    assert response.extra['order_id'] == 'order_202'
    assert 'requested_at' in response.extra

    assert captured_call.get('user_id') == 555
    assert captured_call.get('amount_kopeks') == 25000
    assert captured_call.get('description')


@pytest.mark.anyio('asyncio')
async def test_resolve_wata_payment_status_success():
    paid_at = datetime.now(UTC)
    payment = types.SimpleNamespace(
        id=404,
        user_id=9,
        amount_kopeks=30000,
        currency='RUB',
        status='Paid',
        is_paid=True,
        payment_link_id='wata_link_404',
        order_id='order_404',
        transaction_id=909,
        paid_at=paid_at,
        updated_at=paid_at,
        created_at=paid_at - timedelta(minutes=1),
    )

    class StubWataService:
        async def get_wata_payment_status(self, db, local_payment_id):
            assert local_payment_id == 404
            return {
                'payment': payment,
                'status': 'Paid',
                'is_paid': True,
                'remote_link': {'status': 'Paid'},
                'transaction': {'id': 'tx_404', 'status': 'Paid'},
            }

    query = MiniAppPaymentStatusQuery(
        method='wata',
        localPaymentId=404,
        amountKopeks=30000,
        startedAt='2024-06-01T12:00:00Z',
        payload='wata_payload',
    )

    result = await miniapp._resolve_wata_payment_status(
        StubWataService(),
        db=None,
        user=types.SimpleNamespace(id=9),
        query=query,
    )

    assert result.status == 'paid'
    assert result.external_id == 'wata_link_404'
    assert result.extra['payment_link_id'] == 'wata_link_404'
    assert result.extra['transaction']['id'] == 'tx_404'
    assert result.extra['payload'] == 'wata_payload'
    assert result.extra['started_at'] == '2024-06-01T12:00:00Z'


@pytest.mark.anyio('asyncio')
async def test_resolve_wata_payment_status_uses_payment_link_lookup(monkeypatch):
    created_at = datetime.now(UTC)
    payment = types.SimpleNamespace(
        id=505,
        user_id=7,
        amount_kopeks=15000,
        currency='RUB',
        status='Opened',
        is_paid=False,
        payment_link_id='wata_lookup',
        order_id='order_lookup',
        transaction_id=None,
        paid_at=None,
        updated_at=None,
        created_at=created_at,
    )

    async def fake_get_wata_payment_by_link_id(db, link_id):
        assert link_id == 'wata_lookup'
        return payment

    monkeypatch.setattr(miniapp, 'get_wata_payment_by_link_id', fake_get_wata_payment_by_link_id)

    class StubWataService:
        async def get_wata_payment_status(self, db, local_payment_id):
            assert local_payment_id == 505
            return {
                'payment': payment,
                'status': payment.status,
                'is_paid': False,
                'remote_link': None,
                'transaction': None,
            }

    query = MiniAppPaymentStatusQuery(
        method='wata',
        paymentLinkId='wata_lookup',
        amountKopeks=15000,
    )

    result = await miniapp._resolve_wata_payment_status(
        StubWataService(),
        db=None,
        user=types.SimpleNamespace(id=7),
        query=query,
    )

    assert result.status == 'pending'
    assert result.extra['local_payment_id'] == 505
    assert result.extra['payment_link_id'] == 'wata_lookup'
    assert 'transaction' not in result.extra


@pytest.mark.anyio('asyncio')
async def test_create_payment_link_stars_normalizes_amount(monkeypatch):
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_RATE_RUB', 1000.0, raising=False)
    monkeypatch.setattr(settings, 'BOT_TOKEN', 'test-token', raising=False)

    captured = {}

    class DummyPaymentService:
        def __init__(self, bot):
            captured['bot'] = bot

        async def create_stars_invoice(
            self,
            amount_kopeks,
            description,
            payload,
            *,
            stars_amount=None,
        ):
            captured['amount_kopeks'] = amount_kopeks
            captured['description'] = description
            captured['payload'] = payload
            captured['stars_amount'] = stars_amount
            return 'https://invoice.example'

    class DummySession:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True
            captured['session_closed'] = True

    class DummyBot:
        def __init__(self, token):
            captured['bot_token'] = token
            self.session = DummySession()

    async def fake_resolve_user(db, init_data):
        return types.SimpleNamespace(id=7, telegram_id=7, language='ru'), {}

    monkeypatch.setattr(miniapp, 'PaymentService', DummyPaymentService)
    monkeypatch.setattr(miniapp, 'create_bot', lambda token=None, **kwargs: DummyBot(token or settings.BOT_TOKEN))
    monkeypatch.setattr(miniapp, '_resolve_user_from_init_data', fake_resolve_user)

    payload = MiniAppPaymentCreateRequest(
        initData='data',
        method='stars',
        amountKopeks=101000,
    )

    response = await miniapp.create_payment_link(payload, db=types.SimpleNamespace())

    assert response.payment_url == 'https://invoice.example'
    assert response.amount_kopeks == 100000
    assert response.extra['stars_amount'] == 1
    assert response.extra['requested_amount_kopeks'] == 101000
    assert captured['amount_kopeks'] == 100000
    assert captured['stars_amount'] == 1
    assert captured['bot_token'] == 'test-token'
    assert captured.get('session_closed') is True


@pytest.mark.anyio('asyncio')
async def test_get_payment_methods_exposes_stars_min_amount(monkeypatch):
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_RATE_RUB', 999.99, raising=False)

    async def fake_resolve_user(db, init_data):
        return types.SimpleNamespace(id=1, language='ru'), {}

    monkeypatch.setattr(miniapp, '_resolve_user_from_init_data', fake_resolve_user)

    payload = MiniAppPaymentMethodsRequest(initData='abc')

    response = await miniapp.get_payment_methods(payload, db=types.SimpleNamespace())

    stars_method = next((method for method in response.methods if method.id == 'stars'), None)
    assert stars_method is not None
    assert stars_method.min_amount_kopeks == 99999
    assert stars_method.amount_step_kopeks == 99999
    assert stars_method.integration_type == MiniAppPaymentIntegrationType.REDIRECT
    assert stars_method.iframe_config is None


@pytest.mark.anyio('asyncio')
async def test_get_payment_methods_includes_wata(monkeypatch):
    monkeypatch.setattr(settings, 'WATA_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'WATA_ACCESS_TOKEN', 'token', raising=False)
    monkeypatch.setattr(settings, 'WATA_TERMINAL_PUBLIC_ID', 'terminal', raising=False)
    monkeypatch.setattr(settings, 'WATA_MIN_AMOUNT_KOPEKS', 5000, raising=False)
    monkeypatch.setattr(settings, 'WATA_MAX_AMOUNT_KOPEKS', 7500000, raising=False)

    async def fake_resolve_user(db, init_data):
        return types.SimpleNamespace(id=1, language='ru'), {}

    monkeypatch.setattr(miniapp, '_resolve_user_from_init_data', fake_resolve_user)

    payload = MiniAppPaymentMethodsRequest(initData='abc')
    response = await miniapp.get_payment_methods(payload, db=types.SimpleNamespace())

    wata_method = next((method for method in response.methods if method.id == 'wata'), None)

    assert wata_method is not None
    assert wata_method.min_amount_kopeks == 5000
    assert wata_method.max_amount_kopeks == 7500000
    assert wata_method.icon == '🌊'
    assert wata_method.integration_type == MiniAppPaymentIntegrationType.REDIRECT
    assert wata_method.iframe_config is None


@pytest.mark.anyio('asyncio')
async def test_find_recent_deposit_ignores_transactions_before_attempt():
    started_at = datetime(2024, 5, 1, 12, 0, 0, tzinfo=UTC)

    transaction = types.SimpleNamespace(
        id=10,
        amount_kopeks=1000,
        completed_at=None,
        created_at=started_at - timedelta(minutes=1),
    )

    class DummyResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class DummySession:
        def __init__(self, value):
            self._value = value

        async def execute(self, query):
            return DummyResult(self._value)

    result = await miniapp._find_recent_deposit(
        DummySession(transaction),
        user_id=1,
        payment_method=PaymentMethod.TELEGRAM_STARS,
        amount_kopeks=1000,
        started_at=started_at,
    )

    assert result is None


@pytest.mark.anyio('asyncio')
async def test_find_recent_deposit_accepts_recent_transactions():
    started_at = datetime(2024, 5, 1, 12, 0, 0, tzinfo=UTC)

    transaction = types.SimpleNamespace(
        id=11,
        amount_kopeks=1000,
        completed_at=started_at + timedelta(seconds=5),
        created_at=started_at + timedelta(seconds=5),
    )

    class DummyResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class DummySession:
        def __init__(self, value):
            self._value = value

        async def execute(self, query):
            return DummyResult(self._value)

    result = await miniapp._find_recent_deposit(
        DummySession(transaction),
        user_id=1,
        payment_method=PaymentMethod.TELEGRAM_STARS,
        amount_kopeks=1000,
        started_at=started_at,
    )

    assert result is transaction
