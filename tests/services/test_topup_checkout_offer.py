"""«Подтвердить» прямо в сообщении «Зачислено» — вместо «Продолжить оформление» → «Подтвердить».

Проверяется решение, ставить ли кнопку: корзина покупки или продления та же, цена та же, что
человек видел при выборе, денег хватает. Во всех остальных случаях сообщение остаётся прежним.
Корзина читается из Redis-заглушки, тариф, подписка и цена — настоящим кодом на SQLite.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.database.models import Base, Subscription, Tariff, User
from app.handlers.subscription import tariff_purchase
from app.services import spofy_subpage_service as completion, topup_checkout_offer as offer_module
from app.services.payment import common as payment_common
from app.services.topup_checkout_offer import (
    CONFIRM_CALLBACK_PREFIX,
    TopupCheckoutOffer,
    apply_topup_checkout_offer,
    consume_recent_offer,
    is_one_tap_cart,
    parse_confirm_callback,
    resolve_topup_checkout_offer,
)
from app.services.user_cart_service import UserCartService
from tests.fixtures.redis_pipeline import SequentialPipelineMixin
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 7
TELEGRAM_ID = 555000111
SUB_ID = 42
TARIFF_ID = 2
LIFETIME_TARIFF_ID = 4
PRICE_30 = 15900
PRICE_180 = 68900
LIFETIME_PRICE = 500000


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


@pytest.fixture
def cart_service(monkeypatch):
    service = UserCartService()
    service._redis_client = _MockRedis()
    service._initialized = True
    for module in (offer_module, tariff_purchase, completion, payment_common):
        monkeypatch.setattr(module, 'user_cart_service', service)
    return service


@pytest.fixture(autouse=True)
def _spofy_mode(monkeypatch):
    """Как на проде: один тариф на человека, автопокупки нет, СБП-автопродление выключено."""
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False)
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default')
    monkeypatch.setattr(type(settings), 'is_platega_recurrent_enabled', lambda self: False)
    offer_module._recent_offers.clear()
    yield
    offer_module._recent_offers.clear()


async def _seed(db, *, balance: int, with_subscription: bool = True, sub_devices: int = 3, tariff_active: bool = True):
    now = datetime.now(UTC)
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
                is_active=tariff_active,
                traffic_limit_gb=100,
                device_limit=3,
                device_price_kopeks=5000,
                period_prices={'30': PRICE_30, '180': PRICE_180},
                allowed_squads=[],
            ),
            Tariff(
                id=LIFETIME_TARIFF_ID,
                name='👑 ULTIMA',
                is_active=True,
                traffic_limit_gb=0,
                device_limit=5,
                device_price_kopeks=100000,
                period_prices={'2222': LIFETIME_PRICE},
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
                end_date=now + timedelta(days=3),
                traffic_limit_gb=100,
                traffic_used_gb=0.0,
                device_limit=sub_devices,
                connected_squads=[],
            )
        )
        await db.commit()


def _use_session(monkeypatch, db) -> None:
    """Решение о кнопке открывает свою сессию — в тесте это та же база."""

    @contextlib.asynccontextmanager
    async def same_session():
        yield db

    monkeypatch.setattr(offer_module, 'AsyncSessionLocal', same_session)
    monkeypatch.setattr(payment_common, 'AsyncSessionLocal', same_session)


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
        'description': 'Продление тарифа ⭐️ Стандартный на 180 дней',
        'traffic_limit_gb': 100,
        'device_limit': 3,
        'allowed_squads': [],
        'discount_percent': 0,
    }
    cart.update(overrides)
    return cart


def _purchase_cart(*, tariff_id: int = TARIFF_ID, price: int = PRICE_30, period: int = 30, **overrides) -> dict:
    cart = {
        'cart_mode': 'tariff_purchase',
        'tariff_checkout_id': 'checkout-1',
        'tariff_id': tariff_id,
        'period_days': period,
        'total_price': price,
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


def _resume_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура «Зачислено» при сохранённой корзине — как её собирает build_topup_success_keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Продолжить оформление', callback_data='return_to_saved_cart')],
            [InlineKeyboardButton(text='Мой баланс', callback_data='menu_balance')],
            [InlineKeyboardButton(text='Главное меню', callback_data='back_to_menu')],
        ]
    )


def _callbacks(keyboard: InlineKeyboardMarkup) -> list[str | None]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def _user(balance: int = 0, language: str = 'ru') -> SimpleNamespace:
    return SimpleNamespace(id=USER_ID, telegram_id=TELEGRAM_ID, language=language, balance_kopeks=balance)


def _offer(cart_mode: str = 'extend', *, period: int = 180, price: int = PRICE_180, balance: int = PRICE_180):
    return TopupCheckoutOffer(
        cart_mode=cart_mode,
        tariff_name='⭐️ Стандартный',
        period_days=period,
        price_kopeks=price,
        balance_kopeks=balance,
        token='0123456789abcdef01234567',
    )


# ── Данные кнопки ────────────────────────────────────────────────────────────


def test_button_data_round_trips_and_fits_telegram_limit():
    offer = _offer(price=9_999_999, balance=999_999_999)

    assert offer.callback_data == f'{CONFIRM_CALLBACK_PREFIX}:0123456789abcdef01234567:9999999:999999999'
    assert len(offer.callback_data.encode()) <= 64, 'Telegram не примет callback_data длиннее 64 байт'
    assert parse_confirm_callback(offer.callback_data) == ('0123456789abcdef01234567', 9_999_999, 999_999_999)


@pytest.mark.parametrize(
    'data',
    [
        None,
        '',
        'return_to_saved_cart',
        'cart_confirm',
        'cart_confirm:token:100',  # нет баланса
        'cart_confirm:token:100:200:300',  # лишнее поле
        'cart_confirm::100:200',  # нет ключа корзины
        'cart_confirm:token:abc:200',
        'cart_confirm:token:100:abc',
        'cart_confirm:token:0:200',  # бесплатное оформление идёт через экран
        'cart_confirm:token:-5:200',
        'cart_confirm:token:300:200',  # в кнопке денег меньше цены — такую кнопку бот не выдаёт
        'tariff_confirm:token:100:200',
    ],
)
def test_foreign_or_broken_button_data_is_rejected(data):
    assert parse_confirm_callback(data) is None


@pytest.mark.parametrize(
    ('cart', 'expected'),
    [
        (_extend_cart(), True),
        (_purchase_cart(), True),
        (_extend_cart(source='cabinet'), True),
        (None, False),
        ({}, False),
        (_extend_cart(source='spofy_subpage'), False),  # корзину страницы подписки оплачивает её же платёж
        (_purchase_cart(cart_mode='daily_tariff_purchase'), False),
        ({'cart_mode': 'gift_purchase', 'tariff_id': TARIFF_ID}, False),
        ({'cart_mode': 'add_devices', 'subscription_id': SUB_ID, 'devices_to_add': 1}, False),
        (_extend_cart(tariff_id=None), False),
    ],
)
def test_only_bot_purchase_and_renewal_carts_are_one_tap(cart, expected):
    assert is_one_tap_cart(cart) is expected


def test_subpage_source_matches_the_subscription_page_service():
    """Признак корзины страницы подписки продублирован (иначе круговой импорт) — значения обязаны совпадать."""
    assert offer_module._SUBPAGE_SOURCE == completion.SUBPAGE_SOURCE


# ── Сообщение: текст и клавиатура ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_renewal_message_gets_confirm_button_instead_of_resume(monkeypatch):
    offer = _offer(balance=PRICE_180)
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(return_value=offer))
    keyboard = _resume_keyboard()

    text, new_keyboard = await apply_topup_checkout_offer(_user(), '✅ Зачислено 589 ₽\n💳 Баланс: 689 ₽', keyboard)

    assert text == ('✅ Зачислено 589 ₽\n💳 Баланс: 689 ₽\n\nПродление: <b>⭐️ Стандартный</b>, 180 дней — <b>689 ₽</b>')
    first = new_keyboard.inline_keyboard[0]
    assert [button.text for button in first] == ['✅ Подтвердить продление']
    assert first[0].callback_data == offer.callback_data
    assert first[0].style == 'success'
    assert _callbacks(new_keyboard)[1:] == ['menu_balance', 'back_to_menu'], 'остальные кнопки прежние'
    assert _callbacks(keyboard)[0] == 'return_to_saved_cart', 'исходная клавиатура не тронута'


@pytest.mark.asyncio
async def test_purchase_message_gets_purchase_wording(monkeypatch):
    offer = _offer('tariff_purchase', period=30, price=PRICE_30, balance=20000)
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(return_value=offer))

    text, keyboard = await apply_topup_checkout_offer(_user(), '✅ Зачислено 100 ₽', _resume_keyboard())

    assert text.endswith('\n\nПокупка: <b>⭐️ Стандартный</b>, 30 дней — <b>159 ₽</b>')
    assert keyboard.inline_keyboard[0][0].text == '✅ Подтвердить покупку'
    assert keyboard.inline_keyboard[0][0].callback_data == offer.callback_data


@pytest.mark.asyncio
async def test_lifetime_period_reads_as_a_word_and_tariff_name_is_escaped(monkeypatch):
    offer = TopupCheckoutOffer('tariff_purchase', 'A<b>&B', 2222, LIFETIME_PRICE, LIFETIME_PRICE, 'ab' * 12)
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(return_value=offer))

    text, _ = await apply_topup_checkout_offer(_user(), 'x', _resume_keyboard())

    assert text == 'x\n\nПокупка: <b>A&lt;b&gt;&amp;B</b>, навсегда — <b>5000 ₽</b>'


@pytest.mark.asyncio
async def test_english_user_gets_english_wording(monkeypatch):
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(return_value=_offer()))

    text, keyboard = await apply_topup_checkout_offer(_user(language='en'), 'x', _resume_keyboard())

    assert 'Renewal: <b>⭐️ Стандартный</b>' in text
    assert keyboard.inline_keyboard[0][0].callback_data.startswith('cart_confirm:')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'keyboard',
    [
        None,
        InlineKeyboardMarkup(inline_keyboard=[]),
        # Корзины нет: первой идёт «Купить подписку» / «Продлить».
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Купить', callback_data='menu_buy')]]),
        # Подарок возвращается своей кнопкой.
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text='К подарку', callback_data='return_to_gift_cart')]]
        ),
        # Кабинетный режим меню: кнопка открывает кабинет, callback у неё нет.
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text='Продолжить', url='https://example.com/subscription')]]
        ),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text='Продолжить оформление', callback_data='return_to_saved_cart'),
                    InlineKeyboardButton(text='Ещё', callback_data='menu_balance'),
                ]
            ]
        ),
    ],
)
async def test_message_without_resume_button_is_left_alone(monkeypatch, keyboard):
    resolve = AsyncMock(return_value=_offer())
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', resolve)

    text, same_keyboard = await apply_topup_checkout_offer(_user(), 'текст', keyboard)

    assert text == 'текст'
    assert same_keyboard is keyboard
    resolve.assert_not_awaited()
    assert consume_recent_offer(USER_ID) is False


@pytest.mark.asyncio
async def test_no_offer_keeps_resume_button(monkeypatch):
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(return_value=None))
    keyboard = _resume_keyboard()

    text, same_keyboard = await apply_topup_checkout_offer(_user(), 'текст', keyboard)

    assert (text, same_keyboard) == ('текст', keyboard)
    assert same_keyboard is keyboard
    assert consume_recent_offer(USER_ID) is False


@pytest.mark.asyncio
async def test_failure_while_building_never_blocks_the_topup_message(monkeypatch):
    """Деньги уже зачислены: сообщение обязано уйти, пусть и с прежней кнопкой."""
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(side_effect=RuntimeError('db down')))
    keyboard = _resume_keyboard()

    text, same_keyboard = await apply_topup_checkout_offer(_user(), 'текст', keyboard)

    assert text == 'текст'
    assert same_keyboard is keyboard
    assert consume_recent_offer(USER_ID) is False


@pytest.mark.asyncio
async def test_unreadable_user_never_blocks_the_topup_message():
    """Объект пользователя отсоединён от сессии (чтение поля падает) — сообщение уходит прежним."""

    class Detached:
        @property
        def id(self):
            raise RuntimeError('detached instance')

    keyboard = _resume_keyboard()

    text, same_keyboard = await apply_topup_checkout_offer(Detached(), 'текст', keyboard)

    assert text == 'текст'
    assert same_keyboard is keyboard


# ── Решение, ставить ли кнопку (настоящая корзина, тариф и цена) ─────────────


@pytest.mark.asyncio
async def test_renewal_cart_that_balance_now_covers_is_offered(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        offer = await resolve_topup_checkout_offer(_user())
        cart_after = await cart_service.get_user_cart(USER_ID)
        saved, _ = await tariff_purchase.load_saved_tariff_cart(db, await db.get(User, USER_ID), dict(cart_after))

    assert offer is not None
    assert (offer.cart_mode, offer.tariff_name, offer.period_days) == ('extend', '⭐️ Стандартный', 180)
    assert (offer.price_kopeks, offer.balance_kopeks) == (PRICE_180, PRICE_180)
    assert offer.token == saved.checkout_token
    assert parse_confirm_callback(offer.callback_data) == (saved.checkout_token, PRICE_180, PRICE_180)
    assert cart_after['total_price'] == PRICE_180, 'решение о кнопке корзину не переписывает'


@pytest.mark.asyncio
async def test_renewal_price_includes_extra_devices_of_the_subscription(monkeypatch, cart_service):
    """Докупленные устройства входят в цену продления — в кнопке та же сумма, что на экране выбора."""
    price = PRICE_30 + 2 * 5000  # 5 устройств при 3 в тарифе, 30 дней
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=price, sub_devices=5)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart(price=price, period=30, device_limit=5))

        offer = await resolve_topup_checkout_offer(_user())

    assert offer is not None and offer.price_kopeks == price


@pytest.mark.asyncio
async def test_purchase_cart_without_subscription_is_offered(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=20000, with_subscription=False)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _purchase_cart())

        offer = await resolve_topup_checkout_offer(_user())

    assert offer is not None
    assert (offer.cart_mode, offer.period_days, offer.price_kopeks, offer.balance_kopeks) == (
        'tariff_purchase',
        30,
        PRICE_30,
        20000,
    )


@pytest.mark.asyncio
async def test_lifetime_purchase_is_offered(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=LIFETIME_PRICE, with_subscription=False)
        _use_session(monkeypatch, db)
        cart = _purchase_cart(tariff_id=LIFETIME_TARIFF_ID, price=LIFETIME_PRICE, period=2222, traffic_limit_gb=0)
        await cart_service.save_user_cart(USER_ID, cart)

        offer = await resolve_topup_checkout_offer(_user())

    assert offer is not None and offer.period_days == 2222 and offer.price_kopeks == LIFETIME_PRICE


@pytest.mark.asyncio
async def test_balance_below_price_keeps_the_checkout_screen(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180 - 1)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        assert await resolve_topup_checkout_offer(_user()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('seen_price', [PRICE_180 - 6890, PRICE_180 + 10000])
async def test_price_changed_since_selection_keeps_the_checkout_screen(monkeypatch, cart_service, seen_price):
    """Человек видел другую сумму (скидка кончилась или цена выросла) — новую показывает экран."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180 + 50000)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart(price=seen_price))

        assert await resolve_topup_checkout_offer(_user()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'cart',
    [
        None,
        _extend_cart(source='spofy_subpage'),
        {'cart_mode': 'gift_purchase', 'tariff_id': TARIFF_ID, 'period_days': 30, 'total_price': PRICE_30},
        {'cart_mode': 'add_devices', 'subscription_id': SUB_ID, 'devices_to_add': 1, 'price_kopeks': 5000},
        _extend_cart(subscription_id=999),  # подписки уже нет
        _extend_cart(period=90, price=35900),  # срока нет в прайсе тарифа
        _extend_cart(total_price='oops'),
    ],
)
async def test_other_carts_keep_the_previous_message(monkeypatch, cart_service, cart):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=500000)
        _use_session(monkeypatch, db)
        if cart is not None:
            await cart_service.save_user_cart(USER_ID, cart)

        assert await resolve_topup_checkout_offer(_user()) is None


@pytest.mark.asyncio
async def test_disabled_tariff_is_not_offered_and_cart_is_left_for_the_screen(monkeypatch, cart_service):
    """Решение о кнопке только читает: корзину с отключённым тарифом удалит экран, сказав причину."""
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=500000, tariff_active=False)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        assert await resolve_topup_checkout_offer(_user()) is None
        assert await cart_service.get_user_cart(USER_ID) is not None


@pytest.mark.asyncio
async def test_sbp_autorenewal_choice_keeps_the_checkout_screen(monkeypatch, cart_service):
    """С включённым СБП-автопродлением на экране оформления есть выбор способа — его не прячем."""
    monkeypatch.setattr(type(settings), 'is_platega_recurrent_enabled', lambda self: True)
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        assert await resolve_topup_checkout_offer(_user()) is None


@pytest.mark.asyncio
async def test_unknown_user_is_not_offered(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        assert await resolve_topup_checkout_offer(_user()) is None
        assert await resolve_topup_checkout_offer(SimpleNamespace(id=None)) is None
        assert await resolve_topup_checkout_offer(None) is None


# ── Сообщение «Зачислено» целиком, как его шлют платёжные системы ───────────


@pytest.mark.asyncio
async def test_topup_success_message_for_renewal(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        text, keyboard = await payment_common.build_topup_success_message(
            payment_common.PaymentCommonMixin(), _user(balance=PRICE_180), 58900
        )

    base = payment_common.topup_success_text(_user(balance=PRICE_180), 58900)
    assert 'Зачислено 589 ₽' in base and 'Баланс: 689 ₽' in base
    assert text == f'{base}\n\nПродление: <b>⭐️ Стандартный</b>, 180 дней — <b>689 ₽</b>'
    assert [button.text for button in keyboard.inline_keyboard[0]] == ['✅ Подтвердить продление']
    callbacks = _callbacks(keyboard)
    assert parse_confirm_callback(callbacks[0]) is not None
    assert callbacks[1:] == ['menu_balance', 'back_to_menu']
    assert 'return_to_saved_cart' not in callbacks, 'двух кнопок про одну корзину нет'


@pytest.mark.asyncio
async def test_topup_success_message_when_money_is_still_short(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=30000)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())

        text, keyboard = await payment_common.build_topup_success_message(
            payment_common.PaymentCommonMixin(), _user(balance=30000), 20000
        )

    assert text == payment_common.topup_success_text(_user(balance=30000), 20000), 'текст прежний'
    assert _callbacks(keyboard) == ['return_to_saved_cart', 'menu_balance', 'back_to_menu']


@pytest.mark.asyncio
async def test_topup_success_message_without_cart_is_unchanged(monkeypatch, cart_service):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=30000)
        _use_session(monkeypatch, db)

        text, keyboard = await payment_common.build_topup_success_message(
            payment_common.PaymentCommonMixin(), _user(balance=30000), 20000
        )

    assert text == payment_common.topup_success_text(_user(balance=30000), 20000), 'текст прежний'
    assert _callbacks(keyboard) == ['menu_buy', 'menu_balance', 'back_to_menu']


# ── Второе сообщение про ту же корзину ───────────────────────────────────────


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_second_resume_message_is_not_sent_after_confirm_button(monkeypatch, cart_service):
    """«Зачислено» уже несёт «Подтвердить» — «Оплата получена, покупка не оформлена» следом не идёт."""
    bot = _bot()
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        user = await db.get(User, USER_ID)

        _, keyboard = await apply_topup_checkout_offer(user, 'x', _resume_keyboard())
        completed = await completion.complete_subpage_carts_after_topup(db, user, bot=bot, credited_kopeks=58900)

    assert parse_confirm_callback(_callbacks(keyboard)[0]) is not None
    assert completed is False
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_resume_message_is_still_sent_when_button_was_not_offered(monkeypatch, cart_service):
    """Денег не хватило — «Зачислено» ушло с прежней кнопкой, второе сообщение идёт как раньше."""
    bot = _bot()
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=30000)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        user = await db.get(User, USER_ID)

        _, keyboard = await apply_topup_checkout_offer(user, 'x', _resume_keyboard())
        await completion.complete_subpage_carts_after_topup(db, user, bot=bot, credited_kopeks=20000)

    assert _callbacks(keyboard)[0] == 'return_to_saved_cart'
    bot.send_message.assert_awaited_once()
    callbacks = _callbacks(bot.send_message.await_args.kwargs['reply_markup'])
    assert callbacks[0] == 'return_to_saved_cart'


@pytest.mark.asyncio
async def test_confirm_button_suppresses_only_one_following_message(monkeypatch, cart_service):
    """Метка одноразовая: следующее пополнение без кнопки получает своё сообщение."""
    bot = _bot()
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        await _seed(db, balance=PRICE_180)
        _use_session(monkeypatch, db)
        await cart_service.save_user_cart(USER_ID, _extend_cart())
        user = await db.get(User, USER_ID)

        await apply_topup_checkout_offer(user, 'x', _resume_keyboard())
        await completion.complete_subpage_carts_after_topup(db, user, bot=bot, credited_kopeks=58900)
        await completion.complete_subpage_carts_after_topup(db, user, bot=bot, credited_kopeks=58900)

    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_stars_message_gets_the_button_but_suppresses_nothing(monkeypatch):
    """У оплаты звёздами сообщение про корзину уходит раньше — глушить после кнопки нечего."""
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', AsyncMock(return_value=_offer()))

    _, keyboard = await apply_topup_checkout_offer(_user(), 'x', _resume_keyboard(), cart_notice_follows=False)

    assert parse_confirm_callback(_callbacks(keyboard)[0]) is not None
    assert consume_recent_offer(USER_ID) is False


@pytest.mark.asyncio
async def test_next_topup_without_button_does_not_inherit_the_mark(monkeypatch):
    """Метка относится к последнему сообщению: следующее «Зачислено» без кнопки её снимает."""
    resolve = AsyncMock(return_value=_offer())
    monkeypatch.setattr(offer_module, 'resolve_topup_checkout_offer', resolve)
    await apply_topup_checkout_offer(_user(), 'x', _resume_keyboard())

    resolve.return_value = None
    await apply_topup_checkout_offer(_user(), 'x', _resume_keyboard())

    assert consume_recent_offer(USER_ID) is False


def test_offer_mark_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(offer_module.time, 'monotonic', lambda: clock[0])

    offer_module._mark_offered(USER_ID)
    clock[0] += offer_module._OFFER_MARK_TTL_SECONDS + 1
    assert consume_recent_offer(USER_ID) is False, 'старая метка не глушит сообщение о новом пополнении'

    offer_module._mark_offered(USER_ID)
    offer_module._mark_offered(USER_ID + 1)
    clock[0] += offer_module._OFFER_MARK_TTL_SECONDS + 1
    offer_module._mark_offered(USER_ID + 2)
    assert set(offer_module._recent_offers) == {USER_ID + 2}, 'просроченные метки не копятся'
    assert consume_recent_offer(None) is False
