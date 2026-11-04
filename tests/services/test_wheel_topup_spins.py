"""Колесо призов: бесплатные спины за пополнения и призы «устройство», «скидка», «ещё спин»."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.database.models import (
    Base,
    PaymentMethod,
    Transaction,
    TransactionType,
    User,
    WheelPrizeType,
    WheelSpin,
    WheelSpinPaymentType,
)
from app.services.wheel_service import FortuneWheelService, FreeSpinState
from app.services.wheel_topup_notifier import build_spin_earned_message, on_payment_completed, spins_earned
from app.utils.subscription_utils import active_wheel_bonus_devices, resolve_hwid_device_limit
from tests.fixtures.sqlite_memory import memory_session


NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _config(**kw):
    base = dict(
        id=1,
        is_enabled=True,
        topup_spins_enabled=True,
        topup_spin_threshold_kopeks=15000,
        topup_spin_value_kopeks=1500,
        topup_spins_since=NOW - timedelta(days=1),
        daily_spin_limit=5,
        spin_cost_stars=10,
        spin_cost_stars_enabled=False,
        spin_cost_days=1,
        spin_cost_days_enabled=False,
        min_subscription_days_for_day_payment=3,
        promo_validity_days=7,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---------- счёт спинов ----------


@pytest.mark.asyncio
async def test_free_spins_counted_from_deposits_won_and_used():
    svc = FortuneWheelService()
    with (
        patch('app.services.wheel_service.get_topup_deposits_kopeks', AsyncMock(return_value=40000)),
        patch('app.services.wheel_service.get_free_spin_counters', AsyncMock(return_value=(1, 2))),
    ):
        state = await svc.get_free_spin_state(AsyncMock(), 7, _config())
    # 400 ₽ / 150 ₽ = 2 спина, +1 выигранный «Ещё спин», −2 прокрученных
    assert state.available == 1
    assert state.progress_kopeks == 10000
    assert state.left_kopeks == 5000


@pytest.mark.asyncio
async def test_free_spins_off_when_disabled():
    svc = FortuneWheelService()
    state = await svc.get_free_spin_state(AsyncMock(), 7, _config(topup_spins_enabled=False))
    assert state == FreeSpinState()


@pytest.mark.asyncio
async def test_deposit_query_counts_only_real_topups(monkeypatch):
    from app.database.crud.wheel import get_free_spin_counters, get_topup_deposits_kopeks

    since = NOW - timedelta(days=1)
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        db.add(User(id=1, telegram_id=10, first_name='U', language='ru', status='active', balance_kopeks=0))

        def tx(amount, method, *, kind=TransactionType.DEPOSIT, when=NOW, done=True):
            db.add(
                Transaction(
                    user_id=1,
                    type=kind.value,
                    amount_kopeks=amount,
                    payment_method=method,
                    is_completed=done,
                    created_at=when,
                )
            )

        tx(19900, PaymentMethod.PLATEGA.value)
        tx(10000, PaymentMethod.TELEGRAM_STARS.value)
        tx(50000, PaymentMethod.MANUAL.value)  # начисление админа — не пополнение
        tx(30000, None)  # бонус без метода (промокод, приз колеса)
        tx(20000, PaymentMethod.YOOKASSA.value, when=since - timedelta(hours=1))  # до включения
        tx(20000, PaymentMethod.YOOKASSA.value, done=False)  # не оплачен
        tx(19900, PaymentMethod.PLATEGA.value, kind=TransactionType.SUBSCRIPTION_PAYMENT)
        db.add(
            WheelSpin(
                user_id=1,
                payment_type=WheelSpinPaymentType.TOPUP_CREDIT.value,
                payment_amount=1,
                payment_value_kopeks=1500,
                prize_type=WheelPrizeType.EXTRA_SPIN.value,
                prize_value=1,
                prize_display_name='Ещё спин',
                prize_value_kopeks=1500,
                is_applied=True,
            )
        )
        await db.commit()

        assert await get_topup_deposits_kopeks(db, 1, since) == 29900
        assert await get_topup_deposits_kopeks(db, 1, None) == 0
        assert await get_free_spin_counters(db, 1) == (1, 1)


# ---------- доступность и спин ----------


@pytest.mark.asyncio
async def test_free_spin_allowed_past_daily_limit():
    svc = FortuneWheelService()
    user = SimpleNamespace(id=1, balance_kopeks=0)
    with (
        patch('app.services.wheel_service.get_or_create_wheel_config', AsyncMock(return_value=_config())),
        patch.object(svc, 'get_free_spin_state', AsyncMock(return_value=FreeSpinState(True, 2, 15000, 0))),
        patch('app.services.wheel_service.get_user_spins_today', AsyncMock(return_value=5)),
        patch('app.services.wheel_service.get_wheel_prizes', AsyncMock(return_value=[SimpleNamespace(id=1)])),
    ):
        availability = await svc.check_availability(AsyncMock(), user)
    assert availability.can_spin is True
    assert availability.can_pay_free is True
    assert availability.free_spins.available == 2


@pytest.mark.asyncio
async def test_no_free_spins_reason_points_to_topups():
    svc = FortuneWheelService()
    user = SimpleNamespace(id=1, balance_kopeks=0)
    with (
        patch('app.services.wheel_service.get_or_create_wheel_config', AsyncMock(return_value=_config())),
        patch.object(svc, 'get_free_spin_state', AsyncMock(return_value=FreeSpinState(True, 0, 15000, 4000))),
        patch('app.services.wheel_service.get_user_spins_today', AsyncMock(return_value=0)),
    ):
        availability = await svc.check_availability(AsyncMock(), user)
    assert availability.can_spin is False
    assert availability.reason == 'no_free_spins'
    assert availability.free_spins.left_kopeks == 11000


@pytest.mark.asyncio
async def test_free_spin_rechecked_under_lock():
    """Два параллельных запроса: второй видит 0 спинов под блокировкой и ничего не выигрывает."""
    svc = FortuneWheelService()
    user = SimpleNamespace(id=1, balance_kopeks=0)
    select_prize = patch.object(svc, '_select_prize')
    with (
        patch.object(
            svc,
            'check_availability',
            AsyncMock(return_value=SimpleNamespace(can_spin=True, can_pay_free=True, reason=None)),
        ),
        patch('app.services.wheel_service.get_or_create_wheel_config', AsyncMock(return_value=_config())),
        patch('app.services.wheel_service.get_wheel_prizes', AsyncMock(return_value=[SimpleNamespace(id=1)])),
        patch('app.database.crud.user.lock_user_for_update', AsyncMock(return_value=user)),
        patch('app.services.wheel_service.get_subscription_by_user_id', AsyncMock(return_value=None)),
        patch.object(type(settings), 'is_multi_tariff_enabled', lambda self: False),
        patch.object(svc, 'get_free_spin_state', AsyncMock(return_value=FreeSpinState(True, 0, 15000, 0))),
        select_prize as selected,
    ):
        result = await svc.spin(AsyncMock(), user, WheelSpinPaymentType.TOPUP_CREDIT.value)
    assert result.success is False
    assert result.error == 'no_free_spins'
    selected.assert_not_called()


# ---------- призы ----------


def _subscription(**kw):
    base = dict(
        id=5,
        is_active=True,
        device_limit=3,
        days_left=20,
        tariff=SimpleNamespace(max_device_limit=None),
        wheel_bonus_devices=0,
        wheel_bonus_devices_until=None,
        updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_device_prize_is_bonus_on_top_of_paid_limit():
    svc = FortuneWheelService()
    sub = _subscription()
    outcome: dict = {}
    assert svc._grant_bonus_devices(sub, 1, outcome) is True
    assert sub.device_limit == 3  # оплаченный лимит не тронут — продление не подорожает
    assert sub.wheel_bonus_devices == 1
    assert active_wheel_bonus_devices(sub) == 1
    with patch.object(type(settings), 'is_devices_selection_enabled', lambda self: True):
        assert resolve_hwid_device_limit(sub) == 4  # в панель уходит лимит с бонусом
    assert outcome['devices'] == 1


@pytest.mark.parametrize(
    'kw',
    [
        {'device_limit': 0},  # безлимит устройств
        {'days_left': 1},  # подписка вот-вот кончится
        {'is_active': False},
        {'device_limit': 5, 'tariff': SimpleNamespace(max_device_limit=5)},  # упёрлись в максимум
    ],
)
def test_device_prize_refused_goes_to_balance(kw):
    svc = FortuneWheelService()
    assert svc._grant_bonus_devices(_subscription(**kw), 1, {}) is False
    assert svc._grant_bonus_devices(None, 1, {}) is False


def test_expired_device_bonus_not_counted():
    sub = _subscription(wheel_bonus_devices=1, wheel_bonus_devices_until=datetime.now(UTC) - timedelta(minutes=1))
    assert active_wheel_bonus_devices(sub) == 0
    with patch.object(type(settings), 'is_devices_selection_enabled', lambda self: True):
        assert resolve_hwid_device_limit(sub) == 3


@pytest.mark.asyncio
async def test_discount_prize_sets_personal_discount():
    svc = FortuneWheelService()
    user = SimpleNamespace(id=1, promo_offer_discount_percent=0, promo_offer_discount_expires_at=None)
    outcome: dict = {}
    await svc._apply_discount_prize(user, SimpleNamespace(prize_value=10), _config(), outcome)
    assert user.promo_offer_discount_percent == 10
    assert user.promo_offer_discount_source == 'wheel'
    assert user.promo_offer_discount_expires_at > datetime.now(UTC) + timedelta(days=6)
    assert outcome['discount_percent'] == 10


@pytest.mark.asyncio
async def test_discount_prize_keeps_bigger_active_discount():
    svc = FortuneWheelService()
    soon = datetime.now(UTC) + timedelta(days=1)
    user = SimpleNamespace(
        id=1, promo_offer_discount_percent=25, promo_offer_discount_expires_at=soon, promo_offer_discount_source='x'
    )
    outcome: dict = {}
    await svc._apply_discount_prize(user, SimpleNamespace(prize_value=10), _config(), outcome)
    assert user.promo_offer_discount_percent == 25
    assert user.promo_offer_discount_source == 'x'
    assert user.promo_offer_discount_expires_at > soon  # срок продлили
    assert outcome['discount_percent'] == 25


def test_prize_messages():
    svc = FortuneWheelService()
    prize = lambda t, v: SimpleNamespace(prize_type=t, prize_value=v, prize_value_kopeks=0)  # noqa: E731
    assert 'Ещё один' in svc._get_prize_message(prize('extra_spin', 1), None, {})
    assert 'Скидка 10%' in svc._get_prize_message(prize('discount', 10), None, {'discount_percent': 10})
    assert 'устройство' in svc._get_prize_message(prize('device_slot', 1), None, {})
    assert 'на баланс' in svc._get_prize_message(prize('traffic_gb', 10), None, {'balance_kopeks': 1500})


# ---------- уведомление ----------


@pytest.mark.parametrize(
    ('after', 'amount', 'expected'),
    [(15000, 15000, 1), (19900, 19900, 1), (14900, 14900, 0), (30000, 10000, 1), (45000, 45000, 3), (20000, 4000, 0)],
)
def test_spins_earned(after, amount, expected):
    assert spins_earned(after, amount, 15000) == expected


def test_spin_earned_message_has_wheel_button():
    with patch('app.services.wheel_topup_notifier.settings.CABINET_URL', 'https://lk.example.org'):
        text, keyboard = build_spin_earned_message('ru', 1, 2)
    assert '+1 спин' in text and 'Спинов: 2' in text
    assert keyboard.inline_keyboard[0][0].url == 'https://lk.example.org/wheel'


@pytest.mark.asyncio
@pytest.mark.parametrize('method', [None, PaymentMethod.MANUAL.value, PaymentMethod.BALANCE.value])
async def test_notifier_ignores_non_topups(method):
    with patch('app.services.wheel_topup_notifier.asyncio.create_task') as create_task:
        await on_payment_completed(
            {'payload': {'payment_method': method, 'user_id': 1, 'amount_kopeks': 19900, 'type': 'deposit'}}
        )
    create_task.assert_not_called()


# ---------- миграция ----------


def test_migration_0138_chain_and_prize_table():
    spec = importlib.util.spec_from_file_location(
        'm0138', Path('migrations/alembic/versions/0138_wheel_topup_spins.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ('0138', '0137')
    assert abs(sum(p[6] for p in module.DEFAULT_PRIZES) - 1.0) < 1e-9
    types = {p[0] for p in module.DEFAULT_PRIZES}
    assert {'device_slot', 'discount', 'extra_spin', 'subscription_days'} <= types
    assert 'nothing' not in types  # мини-бонус: каждый спин что-то даёт
