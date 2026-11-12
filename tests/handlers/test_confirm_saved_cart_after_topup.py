"""Нажатие «Подтвердить» в сообщении «Зачислено».

Корзина, цена и баланс те же, что в кнопке, — сразу зовётся прежний обработчик подтверждения
(он сам пересчитывает цену и списывает). Что-то изменилось — открывается прежний экран
оформления, без списания. Корзина лежит в Redis-заглушке, остальное — настоящий код на SQLite.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, Message, User as TgUser
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Tariff, Transaction, TransactionType, User
from app.handlers.subscription import purchase as purchase_handlers, tariff_purchase as telegram
from app.localization.texts import get_texts
from app.services import subscription_auto_purchase_service as auto_service, topup_checkout_offer as offer_module
from app.services.remnawave_retry_queue import remnawave_retry_queue
from app.services.topup_checkout_offer import resolve_topup_checkout_offer
from app.services.user_cart_service import UserCartService
from tests.fixtures.redis_pipeline import SequentialPipelineMixin
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 7
TELEGRAM_ID = 555000111
SUB_ID = 42
TARIFF_ID = 2
PRICE_30 = 15900
PRICE_180 = 68900

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
    """Нажатие кнопки: копия с другими данными делит с оригиналом сообщение и ответ, как в aiogram."""

    def __init__(self, data, *, message=None, answer=None, bot=None):
        self.data = data
        self.message = message if message is not None else SimpleNamespace(edit_text=AsyncMock())
        self.answer = answer if answer is not None else AsyncMock()
        self.bot = bot if bot is not None else SimpleNamespace()
        self.from_user = SimpleNamespace(id=TELEGRAM_ID, username=None)

    def model_copy(self, *, update):
        return _Callback(update.get('data', self.data), message=self.message, answer=self.answer, bot=self.bot)


@pytest.fixture
def cart_service(monkeypatch):
    service = UserCartService()
    service._redis_client = _MockRedis()
    service._initialized = True

    async def delete_processed(user_id, processed):
        # В бою это Lua-скрипт Redis: удаляется только та корзина, которую оформили (по её ревизии).
        current = await service.get_user_cart(user_id)
        if current and current.get('_cart_revision') == processed.get('_cart_revision'):
            return await service.delete_user_cart(user_id)
        return False

    service.delete_processed_cart = AsyncMock(side_effect=delete_processed)
    for module in (offer_module, telegram, purchase_handlers):
        monkeypatch.setattr(module, 'user_cart_service', service)
    return service


@pytest.fixture(autouse=True)
def _spofy_mode(monkeypatch):
    """Как на проде: один тариф на человека, автопокупки нет, СБП-автопродление выключено."""
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False)
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', False)
    monkeypatch.setattr(type(settings), 'is_platega_recurrent_enabled', lambda self: False)
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
def confirm_handlers(monkeypatch):
    """Прежние обработчики «Подтвердить» — здесь только запоминают, с чем их позвали."""
    handlers = SimpleNamespace(extend=AsyncMock(), purchase=AsyncMock())
    monkeypatch.setattr(telegram, 'confirm_tariff_extend', handlers.extend)
    monkeypatch.setattr(telegram, 'confirm_tariff_purchase', handlers.purchase)
    return handlers


async def _seed(db, *, balance: int, with_subscription: bool = True) -> datetime:
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
                created_at=now,
            ),
            Tariff(
                id=TARIFF_ID,
                name='⭐️ Стандартный',
                is_active=True,
                traffic_limit_gb=100,
                device_limit=3,
                device_price_kopeks=5000,
                period_prices={'30': PRICE_30, '180': PRICE_180},
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
                tariff_id=TARIFF_ID,
                status='active',
                is_trial=False,
                start_date=now - timedelta(days=30),
                end_date=end,
                traffic_limit_gb=100,
                traffic_used_gb=0.0,
                device_limit=3,
                connected_squads=[],
            )
        )
        await db.commit()
    return end


def _use_session(monkeypatch, db) -> None:
    @contextlib.asynccontextmanager
    async def same_session():
        yield db

    monkeypatch.setattr(offer_module, 'AsyncSessionLocal', same_session)


def _extend_cart(*, price: int = PRICE_180, period: int = 180, **overrides) -> dict:
    cart = {
        'cart_mode': 'extend',
        'tariff_id': TARIFF_ID,
        'subscription_id': SUB_ID,
        'period_days': period,
        'total_price': price,
        'user_id': USER_ID,
        'saved_cart': True,
        'missing_amount': 58900,
        'return_to_cart': True,
        'description': 'Продление тарифа',
        'traffic_limit_gb': 100,
        'device_limit': 3,
        'allowed_squads': [],
        'discount_percent': 0,
    }
    cart.update(overrides)
    return cart


def _purchase_cart(**overrides) -> dict:
    cart = {
        'cart_mode': 'tariff_purchase',
        'tariff_checkout_id': 'checkout-1',
        'tariff_id': TARIFF_ID,
        'period_days': 30,
        'total_price': PRICE_30,
        'user_id': USER_ID,
        'saved_cart': True,
        'missing_amount': 5900,
        'return_to_cart': True,
        'description': 'Покупка тарифа',
        'traffic_limit_gb': 100,
        'device_limit': 3,
        'allowed_squads': [],
        'discount_percent': 0,
        'subscription_id': None,
    }
    cart.update(overrides)
    return cart


async def _offered_button(db) -> str:
    """Данные кнопки ровно такие, какие бот поставил бы под «Зачислено» прямо сейчас."""
    user = await db.get(User, USER_ID)
    offer = await resolve_topup_checkout_offer(user)
    assert offer is not None, 'для этой корзины кнопка подтверждения должна ставиться'
    return offer.callback_data


def _screen_callbacks(callback: _Callback) -> list[str | None]:
    keyboard = callback.message.edit_text.await_args.kwargs['reply_markup']
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


async def _payments(db) -> list[Transaction]:
    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == USER_ID,
            Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
        )
    )
    return list(result.scalars().all())


# ── Одно нажатие: сразу прежний обработчик подтверждения ────────────────────


@pytest.mark.asyncio
async def test_renewal_tap_goes_straight_to_existing_confirm(monkeypatch, cart_service, state, confirm_handlers):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))
        user = await db.get(User, USER_ID)

        await confirm_saved_cart(callback, state, user, db)

    confirm_handlers.extend.assert_awaited_once()
    confirm_callback, confirm_user, confirm_db, confirm_state = confirm_handlers.extend.await_args.args
    assert confirm_callback.data == f'tariff_ext_confirm:{SUB_ID}:{TARIFF_ID}:180'
    assert confirm_callback.message is callback.message, 'итог продления заменит это же сообщение'
    assert (confirm_user, confirm_db, confirm_state) == (user, db, state)
    confirm_handlers.purchase.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()
    assert callback.data.startswith('cart_confirm:'), 'исходное нажатие не переписано'
    assert telegram._cart_confirms_in_flight == set()


@pytest.mark.asyncio
async def test_purchase_tap_goes_straight_to_existing_confirm(monkeypatch, cart_service, state, confirm_handlers):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=20000, with_subscription=False)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _purchase_cart())
        button = await _offered_button(db)
        callback = _Callback(button)

        await confirm_saved_cart(callback, state, await db.get(User, USER_ID), db)

    token = button.split(':')[1]
    confirm_handlers.purchase.assert_awaited_once()
    assert confirm_handlers.purchase.await_args.args[0].data == f'tariff_confirm:{TARIFF_ID}:30:{token}'
    confirm_handlers.extend.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()
    # Обработчик покупки сверяет корзину из состояния с ключом в кнопке — она должна быть на месте.
    checkout = (await state.get_data())['restored_tariff_checkout']
    assert checkout['cart']['tariff_id'] == TARIFF_ID and checkout['cart']['period_days'] == 30
    assert checkout['identity']['tariff_checkout_id'] == 'checkout-1'


# ── Что-то изменилось: прежний экран оформления, без списания ───────────────


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['price', 'balance_up', 'balance_down', 'cart'])
async def test_changed_checkout_opens_the_screen_instead_of_charging(
    monkeypatch, cart_service, state, confirm_handlers, change
):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180 + 5000)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))
        user = await db.get(User, USER_ID)
        tariff = await db.get(Tariff, TARIFF_ID)

        if change == 'price':
            tariff.period_prices = {'30': PRICE_30, '180': PRICE_180 + 1000}
        elif change == 'balance_up':
            user.balance_kopeks += 10000
        elif change == 'balance_down':
            user.balance_kopeks -= 1000  # на продление всё ещё хватает, но это уже не тот баланс
        else:
            await cart_service.save_user_cart(USER_ID, _extend_cart(price=PRICE_30, period=30))
        await db.commit()

        await confirm_saved_cart(callback, state, user, db)
        payments = await _payments(db)

    confirm_handlers.extend.assert_not_awaited()
    confirm_handlers.purchase.assert_not_awaited()
    assert payments == []
    callback.message.edit_text.assert_awaited_once()
    period = 30 if change == 'cart' else 180
    assert f'tariff_ext_confirm:{SUB_ID}:{TARIFF_ID}:{period}' in _screen_callbacks(callback), (
        'открыт экран оформления с прежней кнопкой «Подтвердить» и актуальной ценой'
    )
    assert telegram._cart_confirms_in_flight == set()


@pytest.mark.asyncio
async def test_money_spent_since_the_message_opens_the_still_short_screen(
    monkeypatch, cart_service, state, confirm_handlers
):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))
        user = await db.get(User, USER_ID)
        user.balance_kopeks = 10000
        await db.commit()

        await confirm_saved_cart(callback, state, user, db)

    confirm_handlers.extend.assert_not_awaited()
    callback.message.edit_text.assert_awaited_once()
    assert 'Не хватает: <b>589 ₽</b>' in callback.message.edit_text.await_args.args[0]
    assert not any((data or '').startswith('tariff_ext_confirm:') for data in _screen_callbacks(callback))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('custom_period', 'expected'),
    [(False, True), (True, False)],
)
async def test_one_tap_is_only_for_periods_from_the_price_list(custom_period, expected):
    tariff = SimpleNamespace(id=TARIFF_ID, period_prices={'30': PRICE_30})
    saved = telegram.SavedTariffCart(
        user_id=USER_ID,
        cart_mode='tariff_purchase',
        cart_data={},
        checkout_identity={'tariff_checkout_id': 'c'},
        tariff=tariff,
        subscription=None,
        period=45 if custom_period else 30,
        custom_traffic_gb=None,
        traffic_limit_gb=100,
        device_limit=3,
        total_price=PRICE_30,
        original_price=PRICE_30,
    )

    assert (telegram.one_tap_confirm_callback(saved) is not None) is expected


@pytest.mark.parametrize(
    'overrides',
    [
        {'custom_traffic_gb': 250},  # свой объём трафика подтверждается на экране
        {'total_price': 0},  # бесплатное оформление — тоже через экран
        {'cart_mode': 'daily_tariff_purchase'},
        {'cart_mode': 'extend'},  # продление без подписки
    ],
)
def test_special_checkouts_stay_on_the_screen(overrides):
    fields = {
        'user_id': USER_ID,
        'cart_mode': 'tariff_purchase',
        'cart_data': {},
        'checkout_identity': {'tariff_checkout_id': 'c'},
        'tariff': SimpleNamespace(id=TARIFF_ID, period_prices={'30': PRICE_30}),
        'subscription': None,
        'period': 30,
        'custom_traffic_gb': None,
        'traffic_limit_gb': 100,
        'device_limit': 3,
        'total_price': PRICE_30,
        'original_price': PRICE_30,
    }
    fields.update(overrides)

    assert telegram.one_tap_confirm_callback(telegram.SavedTariffCart(**fields)) is None


# ── Отказы: прежние сообщения ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_cart_gets_the_previous_alert(monkeypatch, cart_service, state, confirm_handlers):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))
        await cart_service.delete_user_cart(USER_ID)

        await confirm_saved_cart(callback, state, await db.get(User, USER_ID), db)

    callback.answer.assert_awaited_once_with('❌ Сохраненная корзина не найдена', show_alert=True)
    confirm_handlers.extend.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_tariff_gets_the_previous_alert_and_cart_is_dropped(
    monkeypatch, cart_service, state, confirm_handlers
):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))
        (await db.get(Tariff, TARIFF_ID)).is_active = False
        await db.commit()

        await confirm_saved_cart(callback, state, await db.get(User, USER_ID), db)
        cart_after = await cart_service.get_user_cart(USER_ID)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs['show_alert'] is True
    assert 'недоступен' in callback.answer.await_args.args[0]
    assert cart_after is None
    confirm_handlers.extend.assert_not_awaited()
    assert telegram._cart_confirms_in_flight == set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    ['broken_button', 'subpage_cart', 'addon_cart', 'inaccessible_message'],
)
async def test_everything_else_takes_the_previous_resume_path(monkeypatch, cart_service, state, confirm_handlers, case):
    """Кнопка не наша, корзина другого вида или сообщение уже нельзя изменить — прежний обработчик."""
    resume = AsyncMock()
    monkeypatch.setattr(purchase_handlers, 'return_to_saved_cart', resume)
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))
        if case == 'broken_button':
            callback.data = 'cart_confirm:zzz'
        elif case == 'subpage_cart':
            await cart_service.save_user_cart(USER_ID, _extend_cart(source='spofy_subpage'))
        elif case == 'addon_cart':
            await cart_service.save_user_cart(
                USER_ID, {'cart_mode': 'add_devices', 'subscription_id': SUB_ID, 'devices_to_add': 1}
            )
        else:
            callback.message = InaccessibleMessage(chat=Chat(id=TELEGRAM_ID, type='private'), message_id=5)
        user = await db.get(User, USER_ID)

        await confirm_saved_cart(callback, state, user, db)

    resume.assert_awaited_once_with(callback, state, user, db)
    confirm_handlers.extend.assert_not_awaited()
    confirm_handlers.purchase.assert_not_awaited()


# ── Двойное нажатие ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_tap_while_first_is_processing_is_not_queued_for_a_charge(
    monkeypatch, cart_service, state, confirm_handlers
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_confirm(*args, **kwargs):
        entered.set()
        await asyncio.wait_for(release.wait(), 5)

    confirm_handlers.extend.side_effect = slow_confirm
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180 * 3)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        button = await _offered_button(db)
        user = await db.get(User, USER_ID)
        first_tap, second_tap = _Callback(button), _Callback(button)

        first = asyncio.create_task(confirm_saved_cart(first_tap, state, user, db))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            await confirm_saved_cart(second_tap, state, user, db)
        finally:
            release.set()
            await asyncio.wait_for(first, 5)

    confirm_handlers.extend.assert_awaited_once()
    second_tap.answer.assert_awaited_once()
    assert second_tap.answer.await_args.args[0] == get_texts('ru').t('TARIFF_PURCHASE_IN_PROGRESS', '')
    assert second_tap.answer.await_args.kwargs['show_alert'] is True
    second_tap.message.edit_text.assert_not_awaited()
    assert telegram._cart_confirms_in_flight == set(), 'после завершения метка снята'


@pytest.mark.asyncio
async def test_failed_confirm_does_not_leave_the_person_locked_out(monkeypatch, cart_service, state, confirm_handlers):
    confirm_handlers.extend.side_effect = RuntimeError('panel down')
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        callback = _Callback(await _offered_button(db))

        with pytest.raises(RuntimeError):
            await confirm_saved_cart(callback, state, await db.get(User, USER_ID), db)

    assert telegram._cart_confirms_in_flight == set()


# ── Сквозная проверка с настоящим списанием ─────────────────────────────────


class _PanelStub:
    async def update_remnawave_user(self, *args, **kwargs):
        return None

    async def create_remnawave_user(self, *args, **kwargs):
        return None


class _AdminNotifyStub:
    def __init__(self, bot):
        self.bot = bot

    async def send_subscription_purchase_notification(self, *args, **kwargs):
        return None


@pytest.fixture
def real_renewal(monkeypatch):
    """Настоящее продление: списание, срок и запись о платеже — в базе; панель и админ-чат — заглушки."""
    monkeypatch.setattr(telegram, 'SubscriptionService', _PanelStub)
    monkeypatch.setattr(telegram, 'should_create_panel_account', AsyncMock(return_value=False))
    monkeypatch.setattr(telegram, 'AdminNotificationService', _AdminNotifyStub)
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: None)


@pytest.mark.asyncio
async def test_one_tap_renews_and_charges_exactly_once(monkeypatch, cart_service, state, real_renewal):
    """589 ₽ пополнено, на балансе 689 ₽ + 1 ₽: одно нажатие — продление на 180 дней и одно списание."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        old_end = await _seed(db, balance=PRICE_180 + 100)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        button = await _offered_button(db)
        callback = _Callback(button)

        await confirm_saved_cart(callback, state, await db.get(User, USER_ID), db)

        db.expire_all()
        balance_after = (await db.get(User, USER_ID)).balance_kopeks
        end_after = (await db.get(Subscription, SUB_ID)).end_date
        payments = await _payments(db)
        cart_after = await cart_service.get_user_cart(USER_ID)

        # Второе нажатие той же кнопки (сообщение Telegram обновил не сразу).
        repeat = _Callback(button)
        await confirm_saved_cart(repeat, state, await db.get(User, USER_ID), db)
        db.expire_all()
        balance_after_repeat = (await db.get(User, USER_ID)).balance_kopeks
        payments_after_repeat = await _payments(db)

    assert balance_after == 100
    assert end_after.replace(tzinfo=UTC) == old_end + timedelta(days=180)
    assert [abs(payment.amount_kopeks) for payment in payments] == [PRICE_180]
    assert cart_after is None, 'оформленная корзина удалена'
    success_text = callback.message.edit_text.await_args.args[0]
    assert 'Подписка продлена' in success_text and 'Списано: 689 ₽' in success_text

    assert balance_after_repeat == 100
    assert len(payments_after_repeat) == 1
    repeat.answer.assert_awaited_once_with('❌ Сохраненная корзина не найдена', show_alert=True)


@pytest.mark.asyncio
async def test_old_button_does_not_charge_again_even_if_cart_survived(monkeypatch, cart_service, state, real_renewal):
    """Денег на два продления, корзина осталась (её не удалил кабинет): старая кнопка ведёт на экран."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180 * 2)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        button = await _offered_button(db)

        await confirm_saved_cart(_Callback(button), state, await db.get(User, USER_ID), db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        repeat = _Callback(button)
        await confirm_saved_cart(repeat, state, await db.get(User, USER_ID), db)
        db.expire_all()
        balance_after = (await db.get(User, USER_ID)).balance_kopeks
        payments = await _payments(db)

    assert balance_after == PRICE_180, 'списано одно продление, не два'
    assert len(payments) == 1
    repeat.message.edit_text.assert_awaited_once()
    assert f'tariff_ext_confirm:{SUB_ID}:{TARIFF_ID}:180' in _screen_callbacks(repeat), (
        'второе продление возможно только осознанно — через экран оформления'
    )


@pytest.fixture
def real_purchase(monkeypatch, cart_service):
    """Настоящая покупка из корзины: резерв платежа, списание и подписка — в базе."""
    monkeypatch.setattr(auto_service, 'user_cart_service', cart_service)
    monkeypatch.setattr(auto_service, 'SubscriptionService', _PanelStub)
    monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', AsyncMock())
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: None)


@pytest.mark.asyncio
async def test_one_tap_purchase_creates_subscription_and_charges_exactly_once(
    monkeypatch, cart_service, state, real_purchase
):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=20000, with_subscription=False)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _purchase_cart())
        button = await _offered_button(db)
        callback = _Callback(button)

        await confirm_saved_cart(callback, state, await db.get(User, USER_ID), db)

        db.expire_all()
        balance_after = (await db.get(User, USER_ID)).balance_kopeks
        payments = await _payments(db)
        subscriptions = list((await db.execute(select(Subscription).where(Subscription.user_id == USER_ID))).scalars())
        bought = [(sub.tariff_id, sub.status, sub.is_trial) for sub in subscriptions]
        cart_after = await cart_service.get_user_cart(USER_ID)

        repeat = _Callback(button)
        await confirm_saved_cart(repeat, state, await db.get(User, USER_ID), db)
        db.expire_all()
        balance_after_repeat = (await db.get(User, USER_ID)).balance_kopeks
        payments_after_repeat = await _payments(db)

    assert balance_after == 20000 - PRICE_30
    assert [(abs(payment.amount_kopeks), payment.is_completed) for payment in payments] == [(PRICE_30, True)]
    assert bought == [(TARIFF_ID, 'active', False)]
    assert cart_after is None
    success_text = callback.message.edit_text.await_args.args[0]
    assert '159 ₽' in success_text and '⭐️ Стандартный' in success_text

    assert balance_after_repeat == 20000 - PRICE_30
    assert len(payments_after_repeat) == 1
    repeat.answer.assert_awaited_once_with('❌ Сохраненная корзина не найдена', show_alert=True)


# ── Настоящий объект нажатия aiogram ────────────────────────────────────────


def test_callback_copy_keeps_message_and_bot_and_changes_only_data():
    """Прежнему обработчику уходит копия нажатия: ответ и правка сообщения идут тем же ботом."""
    bot = MagicMock(spec=Bot)
    chat = Chat(id=TELEGRAM_ID, type='private')
    message = Message(message_id=5, date=datetime.now(UTC), chat=chat, text='Зачислено').as_(bot)
    original = CallbackQuery(
        id='tap-1',
        from_user=TgUser(id=TELEGRAM_ID, is_bot=False, first_name='U'),
        chat_instance='ci',
        message=message,
        data='cart_confirm:0123456789abcdef01234567:68900:68900',
    ).as_(bot)

    copy = original.model_copy(update={'data': f'tariff_ext_confirm:{SUB_ID}:{TARIFF_ID}:180'})

    assert copy.data == f'tariff_ext_confirm:{SUB_ID}:{TARIFF_ID}:180'
    assert original.data == 'cart_confirm:0123456789abcdef01234567:68900:68900'
    assert (copy.id, copy.from_user, copy.chat_instance) == (original.id, original.from_user, original.chat_instance)
    assert copy.message is original.message
    assert copy.bot is bot
