from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import settings
from app.database.crud.subscription import (
    extend_subscription,
    reconcile_subscription_traffic_limit,
    reconcile_tariff_traffic_limit,
)
from app.database.models import Base, Subscription, SubscriptionStatus, Tariff, User
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


async def _limit_after(monkeypatch, action, *, limit=100, tariff_limit=50):
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', True)
    now = datetime.now(UTC)
    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=0))
        tariff = Tariff(
            id=1,
            name='С Обходами',
            description='',
            is_active=True,
            traffic_limit_gb=tariff_limit,
            custom_traffic_enabled=False,
            device_limit=3,
            allowed_squads=['squad-1'],
            period_prices={'30': 31_000},
            display_order=1,
        )
        db.add(tariff)
        db.add(
            Subscription(
                id=10,
                remnawave_short_id='sub10',
                user_id=1,
                status=SubscriptionStatus.ACTIVE.value,
                is_trial=False,
                start_date=now - timedelta(days=10),
                end_date=now + timedelta(days=20),
                traffic_limit_gb=limit,
                traffic_used_gb=12.0,
                purchased_traffic_gb=0,
                device_limit=3,
                tariff_id=1,
                connected_squads=['squad-1'],
            )
        )
        await db.commit()
        subscription = await db.get(Subscription, 10)
        await action(db, subscription, tariff)
        await db.commit()
        await db.refresh(subscription)
        return subscription.traffic_limit_gb


async def test_paid_renewal_starts_the_new_term_on_the_tariff_limit(monkeypatch):
    assert await _limit_after(monkeypatch, lambda db, s, t: extend_subscription(db, s, 30)) == 50


async def test_bonus_days_keep_the_limit_of_the_paid_term(monkeypatch):
    assert await _limit_after(monkeypatch, lambda db, s, t: extend_subscription(db, s, 3, new_term=False)) == 100
    assert (
        await _limit_after(monkeypatch, lambda db, s, t: reconcile_tariff_traffic_limit(db, s, new_term=False)) == 100
    )


async def test_panel_update_keeps_the_limit_of_the_paid_term(monkeypatch):
    assert await _limit_after(monkeypatch, lambda db, s, t: reconcile_subscription_traffic_limit(db, s, t)) == 100


async def test_a_raised_or_unlimited_tariff_applies_right_away(monkeypatch):
    reconcile = lambda db, s, t: reconcile_subscription_traffic_limit(db, s, t)  # noqa: E731
    assert await _limit_after(monkeypatch, reconcile, limit=30) == 50
    assert await _limit_after(monkeypatch, reconcile, tariff_limit=0) == 0


async def test_unlimited_left_on_a_limited_tariff_is_still_fixed(monkeypatch):
    assert (
        await _limit_after(monkeypatch, lambda db, s, t: reconcile_subscription_traffic_limit(db, s, t), limit=0) == 50
    )
    assert (
        await _limit_after(monkeypatch, lambda db, s, t: extend_subscription(db, s, 3, new_term=False), limit=0) == 50
    )
