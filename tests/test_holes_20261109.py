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
