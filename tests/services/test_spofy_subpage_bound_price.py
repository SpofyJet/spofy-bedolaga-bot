"""Spofy: покупка исполняется по цене, зафиксированной при оформлении.

Исполнитель пересчитывает цену на момент исполнения (промо могло истечь,
пропорция за оставшиеся дни — измениться). Для покупок со страницы подписки
это ломало оплату: зачисленная сумма покрывала цену оформления, но не пересчёт,
и деньги оставались на балансе без покупки. Здесь — настоящее списание с баланса
на SQLite: bound-цена побеждает пересчёт, количественные параметры — из корзины.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Transaction, TransactionType, User
from app.services import spofy_subpage_service as completion
from app.services import subscription_auto_purchase_service as auto_service
from app.services.user_cart_service import UserCartService
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 7
SUB_ID = 42
DEVICE_PRICE = 1000
DEVICES_TO_ADD = 2
# Цена оформления: 2 устройства × 1000 ₽/мес. Под неё и пришла оплата.
BOUND_PRICE = DEVICE_PRICE * DEVICES_TO_ADD


class _MockRedis:
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
        import fnmatch

        return 0, [k for k in self.storage if match is None or fnmatch.fnmatch(k, match)]


class _PanelStub:
    """Панель Remnawave в тесте недоступна — синхронизация считается успешной."""

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
    monkeypatch.setattr(completion, 'user_cart_service', service)
    return service


@pytest.fixture(autouse=True)
def _classic_mode(monkeypatch):
    """Классический режим продаж: цена устройства из настроек, одна подписка."""
    monkeypatch.setattr(settings, 'SALES_MODE', 'classic')
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False)
    monkeypatch.setattr(settings, 'PRICE_PER_DEVICE', DEVICE_PRICE)
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)
    monkeypatch.setattr(auto_service, 'SubscriptionService', _PanelStub)
    monkeypatch.setattr(auto_service, 'AdminNotificationService', _AdminNotifyStub)


async def _seed(db, *, balance: int, days_left: int) -> tuple[User, Subscription]:
    now = datetime.now(UTC)
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
        status='active',
        is_trial=False,
        start_date=now - timedelta(days=30),
        end_date=now + timedelta(days=days_left),
        traffic_limit_gb=100,
        traffic_used_gb=0.0,
        device_limit=1,
    )
    db.add_all([user, subscription])
    await db.commit()
    return user, subscription


def _spofy_devices_cart() -> dict:
    return {
        'cart_mode': 'add_devices',
        'subscription_id': SUB_ID,
        'devices_to_add': DEVICES_TO_ADD,
        'price_kopeks': BOUND_PRICE,
        'source': 'spofy_subpage',
        'return_to_cart': True,
        'spofy_price_kopeks': BOUND_PRICE,
        'spofy_requested_kopeks': BOUND_PRICE,
    }


async def _charged(db) -> int:
    db.expire_all()
    user = await db.get(User, USER_ID)
    payments = (
        (
            await db.execute(
                select(Transaction).where(
                    Transaction.user_id == USER_ID,
                    Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
                )
            )
        )
        .scalars()
        .all()
    )
    return abs(payments[0].amount_kopeks) if payments else 0


@pytest.mark.asyncio
async def test_completion_charges_the_checkout_price_not_the_recomputed_one(monkeypatch, cart_service):
    """Пересчёт на момент исполнения (осталось 40 дней) дал бы 2666 ₽ при балансе
    2000 ₽ — старый код оставил бы деньги на балансе без покупки. Bound-цена
    оформления (2000 ₽) списывается, устройства добавляются."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, _ = await _seed(db, balance=BOUND_PRICE, days_left=40)
        await cart_service.save_user_cart(USER_ID, _spofy_devices_cart())

        completed = await completion.complete_subpage_carts_after_topup(
            db, user, bot=None, credited_kopeks=BOUND_PRICE
        )
        subscription = await db.get(Subscription, SUB_ID)
        devices_after = subscription.device_limit
        charged = await _charged(db)

    assert completed is True
    assert devices_after == 1 + DEVICES_TO_ADD, 'устройства добавлены по корзине'
    assert charged == BOUND_PRICE, 'списана цена оформления, а не пересчёт 2666 ₽'


@pytest.mark.asyncio
async def test_same_cart_without_bound_price_behaves_as_before(monkeypatch, cart_service):
    """Бот-корзина без spofy_price_kopeks: пересчёт (2666 ₽) выше баланса (2000 ₽)
    — покупка НЕ исполняется и баланс не трогаем (поведение до фикса)."""
    cart = _spofy_devices_cart()
    del cart['spofy_price_kopeks']
    del cart['spofy_requested_kopeks']
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, _ = await _seed(db, balance=BOUND_PRICE, days_left=40)
        await cart_service.save_user_cart(USER_ID, cart)

        completed = await auto_service._process_single_cart(db, user, cart, bot=None)
        subscription = await db.get(Subscription, SUB_ID)
        devices_after = subscription.device_limit
        charged = await _charged(db)
        balance_after = (await db.get(User, USER_ID)).balance_kopeks

    assert completed is False
    assert devices_after == 1, 'устройства не добавлены'
    assert charged == 0 and balance_after == BOUND_PRICE, 'деньги на месте'


@pytest.mark.asyncio
async def test_orphan_topup_sends_notification_on_real_path(monkeypatch, cart_service):
    """Сквозная проверка через completion: корзина страницы есть, а метки намерения
    нет — покупка не исполняется, юзер получает уведомление с кнопкой возврата."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, _ = await _seed(db, balance=BOUND_PRICE, days_left=40)
        # Метку намерения НЕ ставим (имитируем протухший intent): сохраняем без
        # return_to_cart и затем вырезаем её напрямую из фейка.
        cart = _spofy_devices_cart()
        await cart_service.save_user_cart(USER_ID, cart)
        await cart_service._redis_client.delete(f'cart_topup_intent:{USER_ID}')

        completed = await completion.complete_subpage_carts_after_topup(
            db, user, bot=bot, credited_kopeks=BOUND_PRICE
        )

    assert completed is False
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs['chat_id'] == 555000111
    assert 'баланс' in kwargs['text']
    callbacks = [b.callback_data for row in kwargs['reply_markup'].inline_keyboard for b in row]
    assert callbacks[0] == 'return_to_saved_cart'
