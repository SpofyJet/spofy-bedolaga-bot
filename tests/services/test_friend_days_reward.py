"""Дни за приглашённого друга: обоим, один раз, с потолком и без реферал-фермы."""

import contextlib
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Base, Subscription, SubscriptionEvent, User
from app.services import trial_quest_service as quest


NOW = datetime.now(UTC)


@contextlib.asynccontextmanager
async def _session(monkeypatch):
    stub = sys.modules.get('aiosqlite')
    if stub is not None and not hasattr(stub, 'connect'):
        monkeypatch.delitem(sys.modules, 'aiosqlite', raising=False)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[User.__table__, Subscription.__table__, SubscriptionEvent.__table__]
            )
        )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _user(uid, *, referred_by=None, age_days=0.1, status='active'):
    return User(
        id=uid,
        telegram_id=1000 + uid,
        username=f'u{uid}',
        status=status,
        language='ru',
        referred_by_id=referred_by,
        created_at=NOW - timedelta(days=age_days),
    )


def _sub(uid, *, is_trial=True, alive=True):
    end = NOW + timedelta(days=2) if alive else NOW - timedelta(days=1)
    return Subscription(
        user_id=uid,
        remnawave_short_id=f'sid{uid}',
        status='active' if alive else 'expired',
        is_trial=is_trial,
        start_date=NOW - timedelta(days=1),
        end_date=end,
    )


def _setup(monkeypatch):
    add_days = AsyncMock()
    monkeypatch.setattr(quest, '_add_days', add_days)
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return add_days, bot


async def test_both_get_days_when_friend_connects(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub, inviter_sub = _sub(2), _sub(1, is_trial=False)
        db.add_all([_user(1, age_days=100), _user(2, referred_by=1), inviter_sub, friend_sub])
        await db.commit()
        add_days, bot = _setup(monkeypatch)

        assert await quest.on_first_connected(db, await db.get(User, 2), friend_sub, bot) is True

    assert [call.args[2] for call in add_days.await_args_list] == [2, 2]  # другу и пригласившему по 2 дня
    recipients = {call.kwargs['chat_id'] for call in bot.send_message.await_args_list}
    assert recipients == {1001, 1002}


async def test_reward_is_given_only_once(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub = _sub(2)
        db.add_all([_user(1, age_days=100), _user(2, referred_by=1), _sub(1, is_trial=False), friend_sub])
        await db.commit()
        add_days, bot = _setup(monkeypatch)
        friend = await db.get(User, 2)

        assert await quest.on_first_connected(db, friend, friend_sub, bot) is True
        assert await quest.on_first_connected(db, friend, friend_sub, bot) is False
    assert add_days.await_count == 2


async def test_no_inviter_no_reward(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub = _sub(2)
        db.add_all([_user(2), friend_sub])
        await db.commit()
        add_days, bot = _setup(monkeypatch)

        assert await quest.on_first_connected(db, await db.get(User, 2), friend_sub, bot) is False
    add_days.assert_not_awaited()


async def test_old_account_is_not_a_friend(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub = _sub(2)
        db.add_all([_user(1, age_days=100), _user(2, referred_by=1, age_days=30), _sub(1), friend_sub])
        await db.commit()
        add_days, bot = _setup(monkeypatch)

        assert await quest.on_first_connected(db, await db.get(User, 2), friend_sub, bot) is False
    add_days.assert_not_awaited()


async def test_inviter_cap_is_four_friends(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub = _sub(9)
        db.add_all([_user(1, age_days=100), _user(9, referred_by=1), _sub(1), friend_sub])
        for _ in range(quest.FRIEND_MAX_FRIENDS):
            db.add(SubscriptionEvent(user_id=1, event_type=quest.EVENT_FRIEND_REWARD, message='x', occurred_at=NOW))
        await db.commit()
        add_days, bot = _setup(monkeypatch)

        assert await quest.on_first_connected(db, await db.get(User, 9), friend_sub, bot) is False
    add_days.assert_not_awaited()


async def test_inviter_without_active_subscription_gets_nothing_but_friend_does(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub = _sub(2)
        db.add_all([_user(1, age_days=100), _user(2, referred_by=1), _sub(1, alive=False), friend_sub])
        await db.commit()
        add_days, bot = _setup(monkeypatch)

        assert await quest.on_first_connected(db, await db.get(User, 2), friend_sub, bot) is True
    assert add_days.await_count == 1  # только другу: истёкшую подписку пригласившего не воскрешаем
    assert {call.kwargs['chat_id'] for call in bot.send_message.await_args_list} == {1002}


async def test_expired_friend_subscription_gets_nothing(monkeypatch):
    async with _session(monkeypatch) as db:
        friend_sub = _sub(2, alive=False)
        db.add_all([_user(1, age_days=100), _user(2, referred_by=1), _sub(1), friend_sub])
        await db.commit()
        add_days, bot = _setup(monkeypatch)

        assert await quest.on_first_connected(db, await db.get(User, 2), friend_sub, bot) is False
    add_days.assert_not_awaited()
