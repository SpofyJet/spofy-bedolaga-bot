"""Докупка устройств из сохранённой корзины считается так же, как в кабинете.

Случай из жизни: ULTIMA до 2099 года, устройство стоит разово 1000 ₽. Кнопка
«Продолжить оформление» считала цену за 26 720 дней остатка, получала 890 666 ₽
и отвечала «Не удалось завершить покупку».

База настоящая, подменены только панель Remnawave и уведомления админам.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.cabinet.routes.subscription_modules.devices import get_device_price
from app.config import settings
from app.database.models import Base, Subscription, Tariff, Transaction, TransactionType, User
from app.services import spofy_subpage_service as subpage_service, subscription_auto_purchase_service as auto_service
from app.services.user_cart_service import UserCartService
from app.utils.pricing_utils import calculate_device_addon_price, count_chargeable_devices
from app.webapi.routes import miniapp as miniapp_routes
from tests.fixtures.redis_pipeline import SequentialPipelineMixin
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 7
SUB_ID = 42
TARIFF_ID = 4
ONE_TIME_PRICE = 100_000
MONTHLY_PRICE = 5_000
LIFETIME_END = datetime(2099, 12, 31, tzinfo=UTC)


class _MockRedis(SequentialPipelineMixin):
    def __init__(self):
        self.storage: dict[str, str] = {}

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        return True

    async def get(self, key):
        return self.storage.get(key)

    async def delete(self, key):
        return 1 if self.storage.pop(key, None) is not None else 0

    async def exists(self, key):
        return 1 if key in self.storage else 0

    async def scan(self, cursor=0, match=None, count=50):
        return 0, [k for k in self.storage if match is None or fnmatch.fnmatch(k, match)]


class _PanelStub:
    async def update_remnawave_user(self, db, subscription):
        return None

    async def enable_remnawave_user(self, remnawave_id):
        return None


class _AdminNotifyStub:
    def __init__(self, bot):
        self.bot = bot

    async def send_subscription_update_notification(self, *args, **kwargs):
        return None


@pytest.fixture
def cart_service(monkeypatch):
    service = UserCartService()
    service._redis_client = _MockRedis()
    service._initialized = True

    async def completed_cart_cleanup(user_id, processed):
        return await service.delete_user_cart(user_id)

    service.delete_processed_cart = AsyncMock(side_effect=completed_cart_cleanup)
    monkeypatch.setattr(auto_service, 'user_cart_service', service)
    monkeypatch.setattr(subpage_service, 'user_cart_service', service)
    return service


@pytest.fixture(autouse=True)
def _tariff_mode(monkeypatch):
    monkeypatch.setattr(settings, 'SALES_MODE', 'tariffs')
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(settings, 'DEFAULT_DEVICE_LIMIT', 1)
    monkeypatch.setattr(auto_service, 'SubscriptionService', _PanelStub)
    monkeypatch.setattr(auto_service, 'AdminNotificationService', _AdminNotifyStub)


async def _seed(
    db,
    *,
    flat: bool,
    end_date: datetime,
    device_limit: int,
    tariff_devices: int = 5,
    balance: int = 5_123_878,
) -> tuple[User, Subscription]:
    now = datetime.now(UTC)
    tariff = Tariff(
        id=TARIFF_ID,
        name='Тариф',
        device_limit=tariff_devices,
        device_price_kopeks=ONE_TIME_PRICE if flat else MONTHLY_PRICE,
        device_price_flat=flat,
        period_prices={'30': 15_900},
    )
    user = User(
        id=USER_ID,
        telegram_id=555000111,
        first_name='U',
        status='active',
        language='ru',
        balance_kopeks=balance,
        created_at=now,
    )
    subscription = Subscription(
        id=SUB_ID,
        user_id=USER_ID,
        tariff_id=TARIFF_ID,
        status='active',
        is_trial=False,
        start_date=now - timedelta(days=5),
        end_date=end_date,
        traffic_limit_gb=0,
        traffic_used_gb=0.0,
        device_limit=device_limit,
    )
    db.add_all([tariff, user, subscription])
    await db.commit()
    return user, subscription


def _cart(devices: int, price: int, **extra) -> dict:
    return {
        'cart_mode': 'add_devices',
        'subscription_id': SUB_ID,
        'devices_to_add': devices,
        'price_kopeks': price,
        'return_to_cart': True,
        **extra,
    }


async def _payments(db) -> list[Transaction]:
    db.expire_all()
    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == USER_ID,
            Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
        )
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_button_buys_lifetime_device_at_one_time_price(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, _ = await _seed(db, flat=True, end_date=LIFETIME_END, device_limit=9)
        cart = _cart(1, ONE_TIME_PRICE, source='cabinet')
        await cart_service.save_user_cart(USER_ID, cart)

        completed = await auto_service.resume_addon_cart(db, user, cart, bot=None)

        payments = await _payments(db)
        subscription = await db.get(Subscription, SUB_ID)
        balance_after = (await db.get(User, USER_ID)).balance_kopeks

    assert completed is True
    assert subscription.device_limit == 10
    assert [abs(payment.amount_kopeks) for payment in payments] == [ONE_TIME_PRICE]
    assert balance_after == 5_123_878 - ONE_TIME_PRICE


@pytest.mark.parametrize(
    ('flat', 'days_left', 'device_limit', 'devices'),
    [
        pytest.param(True, None, 9, 1, id='разовая цена, вечная подписка'),
        pytest.param(True, 40, 9, 3, id='разовая цена, обычный срок'),
        pytest.param(False, 40, 5, 2, id='цена за остаток дней'),
        pytest.param(False, 40, 3, 4, id='часть мест бесплатна'),
    ],
)
@pytest.mark.asyncio
async def test_recomputed_price_equals_cabinet_quote(monkeypatch, cart_service, flat, days_left, device_limit, devices):
    """Сравнение с настоящей ценой кабинета: разъедутся формулы — упадёт здесь."""
    end_date = LIFETIME_END if days_left is None else datetime.now(UTC) + timedelta(days=days_left)
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, subscription = await _seed(db, flat=flat, end_date=end_date, device_limit=device_limit)
        quote = await get_device_price(devices=devices, subscription_id=subscription.id, user=user, db=db)
        price = int(quote['total_price_kopeks'])
        cart = _cart(devices, price)
        await cart_service.save_user_cart(USER_ID, cart)

        completed = await auto_service.resume_addon_cart(db, user, cart, bot=None)
        payments = await _payments(db)

    assert price > 0
    assert completed is True
    assert [abs(payment.amount_kopeks) for payment in payments] == [price]


@pytest.mark.asyncio
async def test_seat_inside_tariff_is_added_without_a_charge(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, _ = await _seed(db, flat=False, end_date=datetime.now(UTC) + timedelta(days=40), device_limit=2)
        cart = _cart(1, 6_666)
        await cart_service.save_user_cart(USER_ID, cart)

        completed = await auto_service.resume_addon_cart(db, user, cart, bot=None)

        payments = await _payments(db)
        subscription = await db.get(Subscription, SUB_ID)
        balance_after = (await db.get(User, USER_ID)).balance_kopeks

    assert completed is True
    assert subscription.device_limit == 3
    assert payments == []
    assert balance_after == 5_123_878


@pytest.mark.asyncio
async def test_page_cart_paid_by_its_payment_keeps_checkout_price(monkeypatch, cart_service):
    """Цена, под которую пришли деньги, по-прежнему важнее пересчёта."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, _ = await _seed(db, flat=True, end_date=LIFETIME_END, device_limit=9, balance=90_000)
        cart = _cart(1, 90_000, source='spofy_subpage')

        completed = await auto_service._process_single_cart(db, user, cart, bot=None, bound_price_kopeks=90_000)
        payments = await _payments(db)

    assert completed is True
    assert [abs(payment.amount_kopeks) for payment in payments] == [90_000]


@pytest.mark.parametrize(
    ('stored', 'expected'),
    [
        pytest.param(None, False, id='нет корзины'),
        pytest.param({'cart_mode': 'extend', 'tariff_id': 2, 'period_days': 30}, True, id='корзина бота'),
        pytest.param({'cart_mode': 'extend', 'source': 'cabinet'}, True, id='корзина кабинета'),
        pytest.param({'cart_mode': 'add_devices', 'source': 'spofy_subpage'}, False, id='корзина страницы подписки'),
    ],
)
@pytest.mark.asyncio
async def test_menu_offers_only_carts_payable_from_the_bot(cart_service, stored, expected):
    if stored:
        await cart_service.save_user_cart(USER_ID, stored)

    assert await subpage_service.has_resumable_cart(USER_ID) is expected


@pytest.mark.asyncio
async def test_old_miniapp_route_charges_one_time_price(monkeypatch):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, subscription = await _seed(db, flat=True, end_date=LIFETIME_END, device_limit=9)
        monkeypatch.setattr(miniapp_routes, '_authorize_miniapp_user', AsyncMock(return_value=user))
        monkeypatch.setattr(miniapp_routes, '_ensure_paid_subscription', lambda *args, **kwargs: subscription)
        monkeypatch.setattr(miniapp_routes, 'SubscriptionService', _PanelStub)

        await miniapp_routes.update_subscription_devices_endpoint(
            SimpleNamespace(init_data='x', devices=10, device_limit=10, subscription_id=SUB_ID), db
        )
        payments = await _payments(db)

    assert [abs(payment.amount_kopeks) for payment in payments] == [ONE_TIME_PRICE]
    assert 'дн.' not in payments[0].description


def test_price_helpers():
    assert count_chargeable_devices(4, 3, 5) == 2
    assert count_chargeable_devices(1, 9, 5) == 1
    assert count_chargeable_devices(1, 2, 5) == 0
    assert calculate_device_addon_price(100_000, 1, 26_720, flat=True) == 100_000
    assert calculate_device_addon_price(5_000, 2, 15, flat=False) == 5_000
    assert calculate_device_addon_price(5_000, 2, 15, flat=False, discount_percent=100) == 0
    assert calculate_device_addon_price(5_000, 0, 15, flat=False) == 0
