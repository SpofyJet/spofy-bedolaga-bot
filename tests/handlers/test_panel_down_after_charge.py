"""Панель Remnawave не отвечает в момент, когда человек подтверждает оплату.

Сбой панели 02.11.2026 (≈10 часов): деньги уже списаны и срок записан в базу, но сервис панели
при ошибке делает db.rollback(), а откат помечает протухшими все объекты сессии. Следующее же
чтение поля (tariff.name, user.id) падало с MissingGreenlet, и человек после списания видел
«Не получилось продлить подписку. Попробуйте ещё раз» — 9 из 12 плативших за этот сбой, один
оплатил продление дважды; при смене тарифа запись о платеже не создавалась вовсе.

Здесь всё настоящее (обработчики, сервис панели, SQLite), не отвечает только сама панель.
"""

from __future__ import annotations

import contextlib
import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Tariff, Transaction, TransactionType, User
from app.external.remnawave_api import RemnaWaveAPIError
from app.handlers.subscription import purchase as purchase_handlers, tariff_purchase as telegram
from app.localization.texts import get_texts
from app.services import subscription_auto_purchase_service as auto_service, topup_checkout_offer as offer_module
from app.services.remnawave_retry_queue import remnawave_retry_queue
from app.services.subscription_service import SubscriptionService
from app.services.topup_checkout_offer import resolve_topup_checkout_offer
from app.services.user_cart_service import UserCartService
from tests.fixtures.redis_pipeline import SequentialPipelineMixin
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 7
TELEGRAM_ID = 555000111
SUB_ID = 42
PANEL_ID = 9001
STANDARD_ID = 2
BYPASS_ID = 3
PRICE_30 = 17900
PRICE_BYPASS_30 = 31000

confirm_tariff_extend = inspect.unwrap(telegram.confirm_tariff_extend)
confirm_instant_switch = inspect.unwrap(telegram.confirm_instant_switch)
confirm_saved_cart = inspect.unwrap(telegram.confirm_saved_cart_after_topup)


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
        import fnmatch

        return 0, [k for k in self.storage if match is None or fnmatch.fnmatch(k, match)]


class _Callback:
    def __init__(self, data, *, message=None, answer=None, bot=None):
        self.data = data
        self.message = message if message is not None else SimpleNamespace(edit_text=AsyncMock())
        self.answer = answer if answer is not None else AsyncMock()
        self.bot = bot if bot is not None else SimpleNamespace()
        self.from_user = SimpleNamespace(id=TELEGRAM_ID, username=None)

    def model_copy(self, *, update):
        return _Callback(update.get('data', self.data), message=self.message, answer=self.answer, bot=self.bot)

    @property
    def shown(self) -> str:
        """Что человек видит в сообщении после нажатия; пусто — бот ничего не показал."""
        call = self.message.edit_text.await_args
        return call.args[0] if call else ''


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
    for module in (offer_module, telegram, purchase_handlers, auto_service):
        monkeypatch.setattr(module, 'user_cart_service', service)
    return service


@pytest.fixture(autouse=True)
def _spofy_mode(monkeypatch):
    """Как на проде: один тариф на человека, автопокупки нет, СБП-автопродление выключено."""
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False)
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', False)
    monkeypatch.setattr(type(settings), 'is_platega_recurrent_enabled', lambda self: False)
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: None)
    offer_module._recent_offers.clear()
    telegram._cart_confirms_in_flight.clear()
    yield
    offer_module._recent_offers.clear()
    telegram._cart_confirms_in_flight.clear()


@pytest.fixture
def state() -> FSMContext:
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=MemoryStorage(), key=key)


@pytest.fixture
def panel_down(monkeypatch) -> list[str]:
    """Панель отвечает 502 на любой запрос — как 02.11.2026."""
    requests: list[str] = []

    @contextlib.asynccontextmanager
    async def no_panel(self):
        requests.append('request')
        raise RemnaWaveAPIError('Bad Gateway', 502)
        yield  # pragma: no cover

    monkeypatch.setattr(SubscriptionService, 'get_api_client', no_panel)
    return requests


@pytest.fixture
def admin_chat(monkeypatch) -> list[tuple]:
    """Уведомление в админ-чат: читает те же поля, что настоящее, и запоминает их."""
    sent: list[tuple] = []

    class _AdminNotify:
        def __init__(self, bot=None):
            self.bot = bot

        async def send_subscription_purchase_notification(self, db, user, subscription, *args, **kwargs):
            sent.append((user.id, user.balance_kopeks, subscription.id, subscription.tariff_id))

    async def with_service(action):
        return await action(_AdminNotify())

    monkeypatch.setattr(telegram, 'AdminNotificationService', _AdminNotify)
    monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', with_service)
    return sent


async def _seed(db, *, balance: int, with_subscription: bool = True, panel_id: int | None = PANEL_ID) -> datetime:
    now = datetime.now(UTC)
    end = now + timedelta(days=3)
    db.add_all(
        [
            User(
                id=USER_ID,
                telegram_id=TELEGRAM_ID,
                first_name='U',
                status='active',
                language='ru',
                balance_kopeks=balance,
                remnawave_id=panel_id,
                created_at=now,
            ),
            Tariff(
                id=STANDARD_ID,
                name='⭐️ Стандартный',
                is_active=True,
                traffic_limit_gb=0,
                device_limit=3,
                device_price_kopeks=5000,
                period_prices={'30': PRICE_30},
                allowed_squads=[],
            ),
            Tariff(
                id=BYPASS_ID,
                name='🏴‍☠️ С Обходами',
                is_active=True,
                traffic_limit_gb=50,
                device_limit=3,
                device_price_kopeks=5000,
                period_prices={'30': PRICE_BYPASS_30},
                allowed_squads=[],
            ),
        ]
    )
    await db.commit()
    if with_subscription:
        db.add(
            Subscription(
                id=SUB_ID,
                user_id=USER_ID,
                tariff_id=STANDARD_ID,
                status='active',
                is_trial=False,
                start_date=now - timedelta(days=27),
                end_date=end,
                traffic_limit_gb=0,
                traffic_used_gb=0.0,
                device_limit=3,
                connected_squads=[],
                subscription_url='https://sub.example/abc',
            )
        )
        await db.commit()
    return end


async def _payments(db) -> list[int]:
    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == USER_ID,
            Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
            Transaction.is_completed.is_(True),
        )
    )
    return [abs(payment.amount_kopeks) for payment in result.scalars().all()]


# ── Продление ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_renewal_paid_while_panel_is_down_shows_success_not_error(
    monkeypatch, cart_service, state, panel_down, admin_chat
):
    """179 ₽ списаны, срок продлён — человек видит «Подписка продлена», а не «попробуйте ещё раз»."""
    texts = get_texts('ru')
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        old_end = await _seed(db, balance=PRICE_30)
        await cart_service.save_user_cart(USER_ID, {'cart_mode': 'extend', 'subscription_id': SUB_ID})
        callback = _Callback(f'tariff_ext_confirm:{SUB_ID}:{STANDARD_ID}:30')

        await confirm_tariff_extend(callback, await db.get(User, USER_ID), db, state)

        db.expire_all()
        balance_after = (await db.get(User, USER_ID)).balance_kopeks
        end_after = (await db.get(Subscription, SUB_ID)).end_date
        payments = await _payments(db)
        cart_after = await cart_service.get_user_cart(USER_ID)

    assert panel_down, 'до панели дошли — и она не ответила'
    assert (balance_after, payments) == (0, [PRICE_30]), 'списано один раз'
    assert end_after.replace(tzinfo=UTC) == old_end + timedelta(days=30)
    assert callback.shown != texts.t('TARIFF_RENEW_ERROR', ''), 'после списания нельзя показывать «не получилось»'
    assert 'Подписка продлена' in callback.shown and 'Списано: 179 ₽' in callback.shown
    assert cart_after is None, 'оформленная корзина удалена — «Зачислено» не предложит оплатить ещё раз'
    assert admin_chat == [(USER_ID, 0, SUB_ID, STANDARD_ID)], 'продажа видна в админ-чате'


# ── Покупка ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_purchase_paid_while_panel_is_down_shows_payment_accepted(
    monkeypatch, cart_service, state, panel_down, admin_chat
):
    """Первая покупка: списано 179 ₽, подписка создана — «Оплата принята», корзина удалена."""

    @contextlib.asynccontextmanager
    async def same_session():
        yield db

    cart = {
        'cart_mode': 'tariff_purchase',
        'tariff_checkout_id': 'checkout-1',
        'tariff_id': STANDARD_ID,
        'period_days': 30,
        'total_price': PRICE_30,
        'user_id': USER_ID,
        'saved_cart': True,
        'missing_amount': 5900,
        'return_to_cart': True,
        'description': 'Покупка тарифа',
        'traffic_limit_gb': 0,
        'device_limit': 3,
        'allowed_squads': [],
        'discount_percent': 0,
        'subscription_id': None,
    }
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=20000, with_subscription=False, panel_id=None)
        monkeypatch.setattr(offer_module, 'AsyncSessionLocal', same_session)
        await cart_service.save_user_cart(USER_ID, cart)
        user = await db.get(User, USER_ID)
        offer = await resolve_topup_checkout_offer(user)
        callback = _Callback(offer.callback_data)

        await confirm_saved_cart(callback, state, user, db)

        db.expire_all()
        balance_after = (await db.get(User, USER_ID)).balance_kopeks
        payments = await _payments(db)
        bought = [
            (sub.tariff_id, sub.status, sub.is_trial)
            for sub in (await db.execute(select(Subscription).where(Subscription.user_id == USER_ID))).scalars()
        ]
        cart_after = await cart_service.get_user_cart(USER_ID)

    assert panel_down, 'до панели дошли — и она не ответила'
    assert (balance_after, payments) == (20000 - PRICE_30, [PRICE_30]), 'списано один раз'
    assert bought == [(STANDARD_ID, 'active', False)]
    assert 'Оплата принята' in callback.shown and 'Списано: 179 ₽' in callback.shown
    assert cart_after is None
    assert [sale[0] for sale in admin_chat] == [USER_ID], 'продажа видна в админ-чате'


# ── Мгновенная смена тарифа ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tariff_switch_paid_while_panel_is_down_records_the_payment(
    monkeypatch, cart_service, state, panel_down, admin_chat
):
    """Доплата за «С Обходами» списана — запись о платеже есть и человек видит «Тариф изменён»."""
    monkeypatch.setattr(settings, 'TARIFF_SWITCH_UPGRADE_ENABLED', True)
    texts = get_texts('ru')
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=10000)
        callback = _Callback(f'instant_sw_confirm:{BYPASS_ID}')

        await confirm_instant_switch(callback, await db.get(User, USER_ID), db, state)

        db.expire_all()
        charged = 10000 - (await db.get(User, USER_ID)).balance_kopeks
        payments = await _payments(db)
        tariff_after = (await db.get(Subscription, SUB_ID)).tariff_id

    assert panel_down, 'до панели дошли — и она не ответила'
    assert charged > 0 and tariff_after == BYPASS_ID, 'доплата списана, тариф сменён'
    assert payments == [charged], 'списание записано в платежи'
    assert callback.shown != texts.t('TARIFF_SWITCH_ERROR', '')
    assert 'Тариф успешно изменён' in callback.shown and '🏴‍☠️ С Обходами' in callback.shown
    assert admin_chat == [(USER_ID, 10000 - charged, SUB_ID, BYPASS_ID)]


# ── Панель отвечает: лишних запросов нет ────────────────────────────────────


@pytest.mark.asyncio
async def test_nothing_is_reloaded_when_the_session_was_not_rolled_back(monkeypatch):
    from app.services.subscription_service import reload_after_panel_failure

    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=100)
        user = await db.get(User, USER_ID)
        subscription = await db.get(Subscription, SUB_ID)
        refresh = AsyncMock(side_effect=db.refresh)
        monkeypatch.setattr(db, 'refresh', refresh)

        await reload_after_panel_failure(db, user, subscription, None, SimpleNamespace(id=1))
        refresh.assert_not_awaited()

        await db.rollback()
        await reload_after_panel_failure(db, user, subscription, None, SimpleNamespace(id=1))

        assert [call.args[0] for call in refresh.await_args_list] == [user, subscription]
        assert (user.balance_kopeks, subscription.tariff_id) == (100, STANDARD_ID)


# ── «Моя подписка» ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize('panel_id', [None, PANEL_ID])
async def test_my_subscription_sync_survives_panel_outage(monkeypatch, panel_down, panel_id):
    """Ссылки ещё нет (купил во время сбоя): экран «Моя подписка» не должен падать на синхронизации.

    02.11.2026 — 54 нажатия «Моя подписка» у 5 человек закончились ничем: лог ошибки читал
    subscription.id у протухшей подписки и ронял весь обработчик.
    """
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        end = await _seed(db, balance=0, panel_id=panel_id)
        subscription = await db.get(Subscription, SUB_ID)
        subscription.subscription_url = None
        await db.commit()
        user = await db.get(User, USER_ID)

        result = await SubscriptionService().ensure_subscription_synced(db, subscription)

        # Обработчик сразу после этого читает поля подписки и человека.
        seen = (subscription.id, subscription.end_date.replace(tzinfo=UTC), user.telegram_id, user.remnawave_id)

    assert panel_down, 'до панели дошли — и она не ответила'
    assert result == (False, 'sync_failed')
    assert seen == (SUB_ID, end, TELEGRAM_ID, panel_id), 'панель недоступна — показываем то, что в базе'


@pytest.mark.asyncio
async def test_my_subscription_screen_opens_while_panel_is_down(monkeypatch, panel_down):
    """Тот же случай целиком: нажатие «Моя подписка» заканчивается экраном, а не тишиной."""
    from app.database.crud.user import get_user_by_id

    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=0, panel_id=None)
        (await db.get(Subscription, SUB_ID)).subscription_url = None
        await db.commit()
        callback = _Callback('menu_subscription')

        await purchase_handlers.show_subscription_info(callback, await get_user_by_id(db, USER_ID), db)

    assert panel_down, 'до панели дошли — и она не ответила'
    assert '⭐️ Стандартный' in callback.shown, 'экран подписки показан'
    callback.answer.assert_awaited_once()
