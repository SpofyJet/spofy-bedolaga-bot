"""«Подтвердить» из сообщения «Зачислено» на настоящем PostgreSQL: одно списание на одно нажатие.

SQLite не ставит блокировки строк, поэтому одновременные нажатия проверяются здесь: решение о
кнопке читает базу своим соединением, как в бою, а два нажатия идут двумя разными сессиями.
"""

import asyncio
import inspect
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database.crud.user import get_user_by_id
from app.database.models import Base, Subscription, Transaction, User
from app.handlers.subscription import purchase as purchase_handlers, tariff_purchase as telegram
from app.localization.texts import get_texts
from app.services import topup_checkout_offer as offer_module
from app.services.remnawave_retry_queue import remnawave_retry_queue
from app.services.topup_checkout_offer import parse_confirm_callback, resolve_topup_checkout_offer
from app.services.user_cart_service import UserCartService
from tests.fixtures.postgres_db import postgres_session
from tests.handlers.test_confirm_saved_cart_after_topup import (
    PRICE_180,
    SUB_ID,
    USER_ID,
    _AdminNotifyStub,
    _Callback,
    _extend_cart,
    _MockRedis,
    _PanelStub,
    _seed,
)


pytestmark = pytest.mark.postgres

confirm_saved_cart = inspect.unwrap(telegram.confirm_saved_cart_after_topup)


def _state() -> SimpleNamespace:
    return SimpleNamespace(update_data=AsyncMock(), clear=AsyncMock(), get_data=AsyncMock(return_value={}))


@asynccontextmanager
async def _renewal_checkout(postgres_database, monkeypatch, *, balance: int):
    """Человек с подпиской, корзина продления на 180 дней и кнопка, которую бот поставил бы под «Зачислено»."""
    for name, value in {
        'MULTI_TARIFF_ENABLED': False,
        'AUTO_PURCHASE_AFTER_TOPUP_ENABLED': False,
        'RESET_TRAFFIC_ON_PAYMENT': False,
        'ADMIN_NOTIFICATIONS_ENABLED': False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(type(settings), 'is_platega_recurrent_enabled', lambda self: False)
    monkeypatch.setattr(telegram, 'SubscriptionService', _PanelStub)
    monkeypatch.setattr(telegram, 'should_create_panel_account', AsyncMock(return_value=False))
    monkeypatch.setattr(telegram, 'AdminNotificationService', _AdminNotifyStub)
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: None)
    carts = UserCartService()
    carts._redis_client = _MockRedis()
    carts._initialized = True
    for module in (offer_module, telegram, purchase_handlers):
        monkeypatch.setattr(module, 'user_cart_service', carts)
    telegram._cart_confirms_in_flight.clear()
    offer_module._recent_offers.clear()

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        old_end = await _seed(db, balance=balance)
        # Решение о кнопке открывает своё соединение — видит только закоммиченное, как в бою.
        maker = async_sessionmaker(db.bind, expire_on_commit=False, autoflush=False)
        monkeypatch.setattr(offer_module, 'AsyncSessionLocal', maker)
        await carts.save_user_cart(USER_ID, _extend_cart())
        user = await get_user_by_id(db, USER_ID)

        offer = await resolve_topup_checkout_offer(user)
        assert offer is not None
        assert parse_confirm_callback(offer.callback_data) == (offer.token, PRICE_180, balance)

        yield SimpleNamespace(db=db, user=user, carts=carts, button=offer.callback_data, old_end=old_end)
    telegram._cart_confirms_in_flight.clear()


async def _charges(db) -> list[int]:
    return [transaction.amount_kopeks for transaction in await db.scalars(select(Transaction))]


async def test_confirm_button_renews_and_charges_once(postgres_database, monkeypatch):
    async with _renewal_checkout(postgres_database, monkeypatch, balance=PRICE_180) as c:
        tap = _Callback(c.button)

        await confirm_saved_cart(tap, _state(), c.user, c.db)
        user = await c.db.get(User, USER_ID, populate_existing=True)
        subscription = await c.db.get(Subscription, SUB_ID, populate_existing=True)

        assert user.balance_kopeks == 0
        assert subscription.end_date == c.old_end + timedelta(days=180)
        assert await _charges(c.db) == [-PRICE_180]
        assert await c.carts.get_user_cart(USER_ID) is None
        tap.message.edit_text.assert_awaited_once()

        repeat = _Callback(c.button)
        await confirm_saved_cart(repeat, _state(), user, c.db)
        subscription = await c.db.get(Subscription, SUB_ID, populate_existing=True)

        assert subscription.end_date == c.old_end + timedelta(days=180)
        assert await _charges(c.db) == [-PRICE_180]
        repeat.answer.assert_awaited_once_with('❌ Сохраненная корзина не найдена', show_alert=True)


async def test_two_simultaneous_taps_charge_once(postgres_database, monkeypatch):
    """Денег хватает на несколько продлений, второе нажатие приходит, пока первое ещё списывает."""
    balance = PRICE_180 * 3
    async with _renewal_checkout(postgres_database, monkeypatch, balance=balance) as c:
        held, release = asyncio.Event(), asyncio.Event()
        original = telegram.subtract_user_balance

        async def pause_charge(*args, **kwargs):
            held.set()
            await asyncio.wait_for(release.wait(), 10)
            return await original(*args, **kwargs)

        monkeypatch.setattr(telegram, 'subtract_user_balance', pause_charge)
        second_tap = _Callback(c.button)
        async with AsyncSession(c.db.bind, expire_on_commit=False) as other_db:
            first = asyncio.create_task(confirm_saved_cart(_Callback(c.button), _state(), c.user, c.db))
            try:
                await asyncio.wait_for(held.wait(), 5)
                other_user = await get_user_by_id(other_db, USER_ID)
                await asyncio.wait_for(confirm_saved_cart(second_tap, _state(), other_user, other_db), 5)
            finally:
                release.set()
                await asyncio.wait_for(first, 15)
        user = await c.db.get(User, USER_ID, populate_existing=True)
        subscription = await c.db.get(Subscription, SUB_ID, populate_existing=True)

        assert user.balance_kopeks == balance - PRICE_180
        assert subscription.end_date == c.old_end + timedelta(days=180)
        assert await _charges(c.db) == [-PRICE_180]
        second_tap.answer.assert_awaited_once_with(
            get_texts('ru').t('TARIFF_PURCHASE_IN_PROGRESS', ''), show_alert=True
        )
        second_tap.message.edit_text.assert_not_awaited()
