"""Пополнение при истёкшей подписке с автоплатежом и сохранённой корзиной.

Раньше любая сохранённая корзина отменяла автопродление: человек с автоплатежом выбирал
срок, пополнял ровно на цену — и деньги оставались на балансе, а подписка истёкшей.
Теперь корзина продления того же тарифа задаёт срок и потолок цены, корзина под другую
покупку по-прежнему защищает деньги от списания. Код настоящий, база — SQLite, корзины —
Redis-заглушка, панель и админ-чат — заглушки.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Tariff, Transaction, TransactionType, User
from app.services import spofy_subpage_service, subscription_auto_purchase_service as auto_service
from app.services.payment import common as payment_common
from app.services.remnawave_retry_queue import remnawave_retry_queue
from app.services.user_cart_service import UserCartService
from tests.fixtures.sqlite_memory import memory_session
from tests.handlers.test_confirm_saved_cart_after_topup import _MockRedis, _PanelStub


USER_ID = 3
SUB_ID = 30
TARIFF_ID = 2
PRICE_14 = 15900
PRICE_90 = 35900


@pytest.fixture
def cart_service(monkeypatch):
    service = UserCartService()
    service._redis_client = _MockRedis()
    service._initialized = True

    async def delete_processed(user_id, processed):
        current = await service.get_user_cart(user_id)
        if current and current.get('_cart_revision') == processed.get('_cart_revision'):
            return await service.delete_user_cart(user_id)
        return False

    service.delete_processed_cart = AsyncMock(side_effect=delete_processed)
    for module in (payment_common, auto_service, spofy_subpage_service):
        monkeypatch.setattr(module, 'user_cart_service', service)
    return service


@pytest.fixture(autouse=True)
def _prod_like(monkeypatch):
    """Как на проде: автопокупки из корзины нет; панель, админ-чат и кабинет — заглушки."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False)
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', False)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    monkeypatch.setattr(auto_service, 'SubscriptionService', _PanelStub)
    monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', AsyncMock())
    monkeypatch.setattr('app.cabinet.routes.websocket.notify_user_subscription_renewed', AsyncMock())
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: None)


async def _seed(db, *, balance: int, autopay: bool = True, device_limit: int = 3) -> datetime:
    now = datetime.now(UTC)
    end = now - timedelta(days=5)
    db.add_all(
        [
            User(id=USER_ID, telegram_id=None, first_name='U', status='active', language='ru', balance_kopeks=balance),
            Tariff(
                id=TARIFF_ID,
                name='Стандартный',
                is_active=True,
                traffic_limit_gb=0,
                device_limit=3,
                device_price_kopeks=5000,
                period_prices={'14': PRICE_14, '90': PRICE_90},
                allowed_squads=[],
            ),
        ]
    )
    await db.commit()
    db.add(
        Subscription(
            id=SUB_ID,
            user_id=USER_ID,
            tariff_id=TARIFF_ID,
            status='expired',
            is_trial=False,
            start_date=now - timedelta(days=95),
            end_date=end,
            traffic_limit_gb=0,
            traffic_used_gb=0.0,
            device_limit=device_limit,
            connected_squads=[],
            autopay_enabled=autopay,
        )
    )
    await db.commit()
    return end


def _cart(*, mode: str = 'tariff_purchase', period: int = 14, price: int = PRICE_14, **overrides) -> dict:
    cart = {
        'cart_mode': mode,
        'tariff_id': TARIFF_ID,
        'period_days': period,
        'total_price': price,
        'user_id': USER_ID,
        'saved_cart': True,
        'missing_amount': price,
        'return_to_cart': True,
        'subscription_id': SUB_ID,
    }
    cart.update(overrides)
    return cart


async def _state(db) -> tuple[int, datetime, list[int]]:
    db.expire_all()
    user = await db.get(User, USER_ID)
    sub = await db.get(Subscription, SUB_ID)
    rows = await db.execute(
        select(Transaction.amount_kopeks).where(
            Transaction.user_id == USER_ID, Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value
        )
    )
    return user.balance_kopeks, sub.end_date.replace(tzinfo=UTC), [abs(a) for a in rows.scalars().all()]


async def _topup(db, amount: int) -> None:
    user = await db.get(User, USER_ID)
    await payment_common.send_cart_notification_after_topup(user, amount, db, bot=None)


@pytest.mark.asyncio
async def test_cart_for_same_tariff_no_longer_cancels_autopay_renewal(monkeypatch, cart_service):
    """Случай из аудита: выбрал тот же тариф на 14 дней, пополнил ровно на цену — подписка продлена."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_14)
        await cart_service.save_user_cart(USER_ID, _cart())

        await _topup(db, PRICE_14)
        balance, end, payments = await _state(db)
        cart_after = await cart_service.get_user_cart(USER_ID)

    assert balance == 0
    assert payments == [PRICE_14], 'одно списание'
    assert end > datetime.now(UTC) + timedelta(days=13)
    assert cart_after is None, 'оформленная корзина убрана: её «Подтвердить» не спишет второй раз'


@pytest.mark.asyncio
async def test_chosen_period_is_kept_not_the_shortest(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_90)
        await cart_service.save_user_cart(USER_ID, _cart(mode='extend', period=90, price=PRICE_90))

        await _topup(db, PRICE_90)
        balance, end, payments = await _state(db)

    assert payments == [PRICE_90]
    assert balance == 0
    assert end > datetime.now(UTC) + timedelta(days=89), 'продлено на выбранные 90 дней, а не на 14'


@pytest.mark.asyncio
async def test_renewal_dearer_than_the_cart_price_is_left_to_the_person(monkeypatch, cart_service):
    """Корзина покупки без докупленных устройств дешевле продления с ними: молча не списываем больше."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        old_end = await _seed(db, balance=PRICE_14 * 2, device_limit=5)
        await cart_service.save_user_cart(USER_ID, _cart())

        await _topup(db, PRICE_14)
        balance, end, payments = await _state(db)
        cart_after = await cart_service.get_user_cart(USER_ID)

    assert payments == []
    assert balance == PRICE_14 * 2
    assert end == old_end
    assert cart_after is not None, 'корзина ждёт «Подтвердить» человека'


@pytest.mark.parametrize(
    'cart',
    [
        pytest.param(_cart(tariff_id=TARIFF_ID + 1), id='другой-тариф'),
        pytest.param(_cart(mode='add_devices'), id='устройства'),
        pytest.param({'cart_mode': 'gift_purchase', 'total_price': PRICE_14, 'return_to_cart': True}, id='подарок'),
        pytest.param(_cart(source='spofy_subpage'), id='страница-подписки'),
        pytest.param(_cart(custom_traffic_gb=50), id='свой-трафик'),
    ],
)
@pytest.mark.asyncio
async def test_money_for_another_purchase_is_not_spent_on_renewal(monkeypatch, cart_service, cart):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        old_end = await _seed(db, balance=PRICE_90)
        await cart_service.save_user_cart(USER_ID, cart)

        await _topup(db, PRICE_90)
        balance, end, payments = await _state(db)

    assert payments == []
    assert balance == PRICE_90
    assert end == old_end


@pytest.mark.asyncio
async def test_forgotten_cart_without_intent_renews_like_no_cart(monkeypatch, cart_service):
    """Корзина без метки намерения (забытая) больше не отменяет автопродление: самый короткий срок."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_14)
        await cart_service.save_user_cart(
            USER_ID, _cart(mode='extend', period=90, price=PRICE_90, return_to_cart=False)
        )

        await _topup(db, PRICE_14)
        balance, end, payments = await _state(db)

    assert payments == [PRICE_14]
    assert balance == 0
    assert datetime.now(UTC) + timedelta(days=13) < end < datetime.now(UTC) + timedelta(days=15)


@pytest.mark.asyncio
async def test_without_autopay_the_cart_still_waits_for_confirm(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        old_end = await _seed(db, balance=PRICE_14, autopay=False)
        await cart_service.save_user_cart(USER_ID, _cart())

        await _topup(db, PRICE_14)
        balance, end, payments = await _state(db)

    assert payments == []
    assert balance == PRICE_14
    assert end == old_end
