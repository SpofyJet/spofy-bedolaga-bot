import contextlib
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Base, Subscription, SubscriptionEvent, User
from app.services import activation_funnel_service as funnel


@contextlib.asynccontextmanager
async def _session(monkeypatch):
    stub = sys.modules.get('aiosqlite')
    if stub is not None and not hasattr(stub, 'connect'):
        monkeypatch.delitem(sys.modules, 'aiosqlite', raising=False)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [m.__table__ for m in (User, Subscription, SubscriptionEvent)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _trial(uid, hours_ago):
    now = datetime.now(UTC)
    return [
        User(id=uid, telegram_id=1000 + uid, username=f'u{uid}', status='active', language='ru'),
        Subscription(
            id=uid,
            user_id=uid,
            remnawave_short_id=f's{uid}',
            is_trial=True,
            status='active',
            traffic_used_gb=0.0,
            start_date=now - timedelta(hours=hours_ago),
            end_date=now + timedelta(days=2),
            created_at=now - timedelta(hours=hours_ago),
        ),
    ]


@pytest.mark.parametrize('nudge', ['_nudge_idle_trial', '_nudge_idle_trial_2'])
async def test_idle_trial_nudges_skip_who_already_connected(monkeypatch, nudge):
    sent = AsyncMock(return_value=object())
    monkeypatch.setattr(funnel, '_funnel_enabled', lambda: True)
    service = funnel.ActivationFunnelService(bot=MagicMock(), send_func=sent)
    hours = max(funnel.IDLE_TRIAL_HOURS, funnel.IDLE_TRIAL2_HOURS) + 1
    async with _session(monkeypatch) as db:
        db.add_all([*_trial(1, hours), *_trial(2, hours)])
        db.add(
            SubscriptionEvent(user_id=1, event_type=funnel.EVENT_TRIAL_FIRST_CONNECTED, occurred_at=datetime.now(UTC))
        )
        for uid in (1, 2):
            db.add(
                SubscriptionEvent(
                    user_id=uid,
                    event_type=funnel.EVENT_TRIAL_IDLE,
                    occurred_at=datetime.now(UTC) - timedelta(hours=hours),
                    created_at=datetime.now(UTC) - timedelta(hours=hours),
                )
            )
        await db.commit()
        if nudge == '_nudge_idle_trial':
            await db.execute(
                SubscriptionEvent.__table__.delete().where(SubscriptionEvent.event_type == funnel.EVENT_TRIAL_IDLE)
            )
            await db.commit()

        await getattr(service, nudge)(db)

    assert [call.args[0] for call in sent.await_args_list] == [1002]
