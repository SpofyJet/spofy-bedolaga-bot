"""Spofy: открытие страницы подписки пишется событием subpage_opened — раз в сутки на человека."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.cabinet.routes import spofy_subpage as route
from app.database.models import Base, Subscription, SubscriptionEvent, User
from tests.fixtures.sqlite_memory import memory_session


async def _seed(db):
    now = datetime.now(UTC)
    user = User(id=1, telegram_id=1001, first_name='U', status='active', language='ru', created_at=now)
    sub = Subscription(
        id=10,
        user_id=1,
        status='active',
        is_trial=True,
        start_date=now,
        end_date=now + timedelta(days=2),
        traffic_limit_gb=10,
        traffic_used_gb=0.0,
        device_limit=1,
    )
    db.add_all([user, sub])
    await db.commit()
    return user, sub


async def _events(db):
    return (
        (await db.execute(select(SubscriptionEvent).where(SubscriptionEvent.event_type == 'subpage_opened')))
        .scalars()
        .all()
    )


async def test_open_is_recorded_once_a_day(monkeypatch):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        user, sub = await _seed(db)
        await route._record_subpage_open(db, user, sub)
        await route._record_subpage_open(db, user, sub)
        events = await _events(db)
        assert len(events) == 1
        assert events[0].subscription_id == 10
        assert events[0].extra == {'trial': True}

        events[0].created_at = datetime.now(UTC) - timedelta(hours=25)
        await db.commit()
        await route._record_subpage_open(db, user, sub)
        assert len(await _events(db)) == 2


def test_event_name_does_not_mute_funnel_nudges():
    # _already_nudged_recently глушит напоминания по любому событию 'funnel_%'.
    assert not route.SUBPAGE_OPENED_EVENT.startswith('funnel_')
