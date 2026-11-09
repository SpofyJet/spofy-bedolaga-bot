"""Дыры, закрытые 09.11: безлимит за разницу общих пакетов и перенос остатка на тариф дороже."""

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


sys.modules.setdefault('nh3', MagicMock())

from fastapi import HTTPException

from app.cabinet.routes.subscription_modules import traffic as traffic_routes
from app.cabinet.schemas.subscription import TrafficPurchaseRequest
from app.config import settings
from app.database.crud.subscription import carried_seconds_by_value, extend_subscription
from app.database.models import Base, Subscription, SubscriptionStatus, Tariff, User
from app.handlers.subscription.traffic import _traffic_switch_blocked
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)
STANDARD_PRICES = {'14': 11900, '30': 15900, '365': 129000}
BYPASS_PRICES = {'30': 27000, '365': 180000}
PACKAGES = [{'gb': 100, 'price': 15000, 'enabled': True}, {'gb': 0, 'price': 20000, 'enabled': True}]
DAY = 86400


def _tariffs() -> list[Tariff]:
    return [
        Tariff(
            id=2,
            name='Std',
            description='',
            is_active=True,
            traffic_limit_gb=0,
            device_limit=3,
            tier_level=1,
            allowed_squads=['a'],
            period_prices=STANDARD_PRICES,
            display_order=1,
        ),
        Tariff(
            id=3,
            name='Obh',
            description='',
            is_active=True,
            traffic_limit_gb=100,
            device_limit=3,
            tier_level=2,
            allowed_squads=['a', 'b'],
            period_prices=BYPASS_PRICES,
            display_order=2,
        ),
    ]


def _subscription(now: datetime, *, tariff_id: int | None, days: int, limit: int, trial: bool = False) -> Subscription:
    return Subscription(
        id=10,
        remnawave_short_id='s',
        user_id=1,
        status=SubscriptionStatus.ACTIVE.value,
        is_trial=trial,
        start_date=now,
        end_date=now + timedelta(days=days),
        traffic_limit_gb=limit,
        traffic_used_gb=0.0,
        device_limit=3,
        tariff_id=tariff_id,
        connected_squads=['a'],
    )


def _days_left(subscription: Subscription, now: datetime) -> float:
    end = subscription.end_date if subscription.end_date.tzinfo else subscription.end_date.replace(tzinfo=UTC)
    return (end - now).total_seconds() / DAY


def test_carry_to_pricier_tariff_is_by_value():
    carried = carried_seconds_by_value(365 * DAY, (129000, 365), (180000, 365))
    assert carried == pytest.approx(365 * DAY * 129000 / 180000)


def test_carry_to_cheaper_or_equal_tariff_is_day_for_day():
    assert carried_seconds_by_value(100 * DAY, (180000, 365), (129000, 365)) == 100 * DAY
    assert carried_seconds_by_value(100 * DAY, (27000, 30), (27000, 30)) == 100 * DAY


def test_carry_with_broken_rate_is_day_for_day():
    assert carried_seconds_by_value(100 * DAY, (0, 30), (27000, 30)) == 100 * DAY
    assert carried_seconds_by_value(-5, (100, 30), (200, 30)) == 0


@pytest.mark.asyncio
async def test_buying_pricier_tariff_does_not_carry_days_one_to_one(monkeypatch):
    now = datetime.now(UTC)
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=0))
        for tariff in _tariffs():
            db.add(tariff)
        await db.flush()
        subscription = _subscription(now, tariff_id=2, days=365, limit=0)
        db.add(subscription)
        await db.commit()

        result = await extend_subscription(
            db, subscription, 30, tariff_id=3, traffic_limit_gb=100, device_limit=3, connected_squads=['a', 'b']
        )

        # было 395 дней; по стоимости: 30 + 365 × 1290 / 1800 ≈ 291,6
        assert result.tariff_id == 3
        assert _days_left(result, now) == pytest.approx(30 + 365 * 129000 / 180000, abs=0.1)


@pytest.mark.asyncio
async def test_buying_cheaper_tariff_keeps_days(monkeypatch):
    now = datetime.now(UTC)
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=0))
        for tariff in _tariffs():
            db.add(tariff)
        await db.flush()
        subscription = _subscription(now, tariff_id=3, days=100, limit=100)
        db.add(subscription)
        await db.commit()

        result = await extend_subscription(
            db, subscription, 30, tariff_id=2, traffic_limit_gb=0, device_limit=3, connected_squads=['a']
        )

        assert _days_left(result, now) == pytest.approx(130, abs=0.1)


@pytest.mark.asyncio
async def test_renewing_same_tariff_keeps_days(monkeypatch):
    now = datetime.now(UTC)
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=0))
        for tariff in _tariffs():
            db.add(tariff)
        await db.flush()
        subscription = _subscription(now, tariff_id=2, days=100, limit=0)
        db.add(subscription)
        await db.commit()

        result = await extend_subscription(db, subscription, 30, tariff_id=2)

        assert _days_left(result, now) == pytest.approx(130, abs=0.1)


@pytest.mark.asyncio
async def test_cabinet_refuses_package_switch_on_tariff(monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(type(settings), 'get_traffic_packages', lambda self: PACKAGES)
    async with memory_session(monkeypatch, TABLES) as db:
        user = User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=10000)
        db.add(user)
        for tariff in _tariffs():
            db.add(tariff)
        await db.flush()
        db.add(_subscription(now, tariff_id=3, days=30, limit=100))
        await db.commit()

        with pytest.raises(HTTPException) as refused:
            await traffic_routes.switch_traffic_package(
                TrafficPurchaseRequest(gb=0), user=user, db=db, subscription_id=None
            )

        assert refused.value.status_code == 400
        assert refused.value.detail['code'] == 'tariff_traffic_fixed'
        subscription = await db.get(Subscription, 10)
        await db.refresh(user)
        assert subscription.traffic_limit_gb == 100
        assert user.balance_kopeks == 10000


def test_bot_refuses_package_switch_on_tariff_and_trial():
    now = datetime.now(UTC)
    assert _traffic_switch_blocked(_subscription(now, tariff_id=3, days=30, limit=100))
    assert _traffic_switch_blocked(_subscription(now, tariff_id=None, days=3, limit=10, trial=True))
    assert not _traffic_switch_blocked(_subscription(now, tariff_id=None, days=30, limit=100))


# ───────────── подарок: остаток по стоимости в обе стороны ─────────────


def test_gift_carry_keeps_value_downwards() -> None:
    # 20 дней «С Обходами» (270 ₽ за 30) = 34 дня «Стандартного» (159 ₽ за 30).
    carried = carried_seconds_by_value(20 * DAY, (27000, 30), (15900, 30), both_ways=True)
    assert carried / DAY == pytest.approx(20 * 270 / 159, abs=1e-6)
    # Покупка (не подарок) вниз — как раньше, день в день.
    assert carried_seconds_by_value(20 * DAY, (27000, 30), (15900, 30)) == 20 * DAY


def test_gift_carry_upwards_and_equal_match_purchase() -> None:
    up = carried_seconds_by_value(365 * DAY, (129000, 365), (180000, 365), both_ways=True)
    assert up == carried_seconds_by_value(365 * DAY, (129000, 365), (180000, 365))
    assert carried_seconds_by_value(40 * DAY, (15900, 30), (15900, 30), both_ways=True) == 40 * DAY


def test_gift_carry_never_turns_into_forever() -> None:
    # Копеечный тариф подарка: пересчёт дал бы десятки лет → остаётся день в день.
    assert carried_seconds_by_value(300 * DAY, (180000, 365), (100, 365), both_ways=True) == 300 * DAY


def test_gift_carry_with_broken_rates_is_day_for_day() -> None:
    assert carried_seconds_by_value(20 * DAY, (0, 30), (15900, 30), both_ways=True) == 20 * DAY
    assert carried_seconds_by_value(20 * DAY, (27000, 30), (15900, 0), both_ways=True) == 20 * DAY


async def _extend_as_gift(
    monkeypatch, now, *, source: int, target: int, left: int, gift_days: int, trial: bool = False, **kw
):
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=0))
        for tariff in _tariffs():
            db.add(tariff)
        await db.flush()
        subscription = _subscription(now, tariff_id=source, days=left, limit=0, trial=trial)
        db.add(subscription)
        await db.commit()
        await extend_subscription(db, subscription, gift_days, tariff_id=target, commit=False, **kw)
        return _days_left(subscription, now)


async def test_gift_of_cheaper_tariff_keeps_the_value_of_the_rest(monkeypatch) -> None:
    now = datetime.now(UTC)
    as_gift = await _extend_as_gift(
        monkeypatch, now, source=3, target=2, left=20, gift_days=30, carry_value_both_ways=True
    )
    as_purchase = await _extend_as_gift(monkeypatch, now, source=3, target=2, left=20, gift_days=30)

    assert as_gift == pytest.approx(30 + 20 * 270 / 159, abs=0.01)  # 63,96 дня
    assert as_purchase == pytest.approx(50, abs=0.01)


async def test_gift_of_pricier_tariff_is_not_day_for_day(monkeypatch) -> None:
    now = datetime.now(UTC)
    days = await _extend_as_gift(
        monkeypatch, now, source=2, target=3, left=365, gift_days=30, carry_value_both_ways=True
    )
    assert days == pytest.approx(30 + 365 * 1290 / 1800, abs=0.01)  # 291,6, а не 395


async def test_gift_of_the_same_tariff_just_adds_days(monkeypatch) -> None:
    now = datetime.now(UTC)
    days = await _extend_as_gift(
        monkeypatch, now, source=2, target=2, left=40, gift_days=30, carry_value_both_ways=True
    )
    assert days == pytest.approx(70, abs=0.01)


async def test_gift_over_a_trial_is_not_recalculated(monkeypatch) -> None:
    # Пробный остаток по стоимости не пересчитывается: результат тот же, что у покупки.
    now = datetime.now(UTC)
    kwargs = dict(source=3, target=2, left=3, gift_days=30, trial=True)
    as_gift = await _extend_as_gift(monkeypatch, now, carry_value_both_ways=True, **kwargs)
    as_purchase = await _extend_as_gift(monkeypatch, now, **kwargs)

    assert as_gift == pytest.approx(as_purchase, abs=0.01)
    assert as_gift <= 33.01


async def test_gift_carry_failure_falls_back_to_day_for_day(monkeypatch) -> None:
    from app.services.pricing_engine import PricingEngine

    def _boom(*args, **kwargs):
        raise RuntimeError('rates unavailable')

    monkeypatch.setattr(PricingEngine, 'get_comparable_daily_rates', staticmethod(_boom))
    now = datetime.now(UTC)
    days = await _extend_as_gift(
        monkeypatch, now, source=3, target=2, left=20, gift_days=30, carry_value_both_ways=True
    )
    assert days == pytest.approx(50, abs=0.01)
