"""Основная подписка без повторной загрузки строк, уже поднятых в сессию — на PostgreSQL.

Полный синк с панелью поднимает всех людей с подписками и тарифами заранее, а
потом на каждого дважды звал ``get_subscription_by_user_id`` — по три запроса,
ответ которых отбрасывался (объект уже в identity map). Замена должна
выбирать ту же строку, отдавать тот же объект и гасить истёкшую так же.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import selectinload

from app.database.crud.subscription import (
    get_subscription_by_user_id,
    get_subscription_by_user_id_in_session,
)
from app.database.models import Subscription, SubscriptionStatus, Tariff, User
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres

TABLES = [Subscription.__table__, User.__table__, Tariff.__table__]
NOW = datetime.now(UTC)


async def _person(db, telegram_id: int, subscriptions: list[dict]) -> User:
    user = User(telegram_id=telegram_id, first_name='Тест', language='ru')
    db.add(user)
    await db.flush()
    for index, fields in enumerate(subscriptions):
        db.add(
            Subscription(
                user_id=user.id,
                is_trial=fields.pop('is_trial', False),
                remnawave_short_id=f'{telegram_id}-{index}',
                created_at=NOW - timedelta(days=10 - index),
                **fields,
            )
        )
    await db.commit()
    return user


# Порядок выбора: active → trial → прочие; дальше поздний срок, дальше поздняя запись.
CASES = {
    'active_over_later_expired': [
        {'status': 'expired', 'end_date': NOW + timedelta(days=90)},
        {'status': 'active', 'end_date': NOW + timedelta(days=5)},
    ],
    'trial_over_disabled': [
        {'status': 'disabled', 'end_date': NOW + timedelta(days=50)},
        {'status': 'trial', 'end_date': NOW + timedelta(days=2), 'is_trial': True},
    ],
    'later_end_date_wins': [
        {'status': 'expired', 'end_date': NOW - timedelta(days=1)},
        {'status': 'expired', 'end_date': NOW - timedelta(days=3)},
    ],
    'later_created_on_equal_end_date': [
        {'status': 'expired', 'end_date': NOW - timedelta(days=4)},
        {'status': 'expired', 'end_date': NOW - timedelta(days=4)},
    ],
    'single': [{'status': 'active', 'end_date': NOW + timedelta(days=30)}],
}


@pytest.mark.parametrize('case', sorted(CASES))
async def test_same_row_as_full_load_when_preloaded(postgres_database, case):
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _person(db, 1000 + sorted(CASES).index(case), [dict(fields) for fields in CASES[case]])
        expected = await get_subscription_by_user_id(db, user.id)
        db.expunge_all()

        # Как полный синк: все люди с подписками и тарифами — в сессии заранее.
        loaded = (
            (await db.execute(select(User).options(selectinload(User.subscriptions).selectinload(Subscription.tariff))))
            .scalars()
            .all()
        )
        statements: list[str] = []
        listener = lambda *args: statements.append(args[2])  # noqa: E731
        event.listen(db.bind.sync_engine, 'before_cursor_execute', listener)
        try:
            got = await get_subscription_by_user_id_in_session(db, user.id)
        finally:
            event.remove(db.bind.sync_engine, 'before_cursor_execute', listener)

        assert got.id == expected.id
        assert got in loaded[0].subscriptions  # тот же объект из сессии, а не новый
        assert got.user is loaded[0]  # связь заполнена без запроса, как selectinload
        assert len(statements) == 1  # только выбор id; строку, человека и тариф не грузит заново


async def test_falls_back_to_full_load_when_not_in_session(postgres_database):
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _person(db, 2001, [dict(fields) for fields in CASES['active_over_later_expired']])
        expected_id = (await get_subscription_by_user_id(db, user.id)).id
        db.expunge_all()

        got = await get_subscription_by_user_id_in_session(db, user.id)

        assert got.id == expected_id
        assert got.user.telegram_id == 2001  # подгружено обычной загрузкой, без ленивого запроса


async def test_none_without_subscriptions(postgres_database):
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _person(db, 2002, [])
        assert await get_subscription_by_user_id_in_session(db, user.id) is None


async def test_expires_overdue_active_like_full_load(postgres_database):
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _person(db, 2003, [{'status': 'active', 'end_date': NOW - timedelta(hours=1)}])
        db.expunge_all()
        loaded = (
            (await db.execute(select(User).options(selectinload(User.subscriptions).selectinload(Subscription.tariff))))
            .scalars()
            .all()
        )

        got = await get_subscription_by_user_id_in_session(db, user.id)

        assert got is loaded[0].subscriptions[0]
        assert got.status == SubscriptionStatus.EXPIRED.value
        stored = (await db.execute(select(Subscription.status).where(Subscription.id == got.id))).scalar_one()
        assert stored == SubscriptionStatus.EXPIRED.value


async def test_people_without_preloaded_subscriptions_one_query(postgres_database):
    """Как синк теперь: в сессии люди и тарифы, подписок нет — строка одной выборкой, связи из сессии."""
    async with postgres_session(postgres_database, TABLES) as db:
        db.add(Tariff(id=7, name='Тариф', is_active=True, period_prices={'30': 300}))
        await db.flush()
        user = await _person(
            db,
            3001,
            [
                {'status': 'expired', 'end_date': NOW - timedelta(days=2)},
                {'status': 'active', 'end_date': NOW + timedelta(days=9), 'tariff_id': 7},
            ],
        )
        expected_id = (await get_subscription_by_user_id(db, user.id)).id
        db.expunge_all()

        tariffs = (await db.execute(select(Tariff))).scalars().all()
        people = (await db.execute(select(User))).scalars().all()
        statements: list[str] = []
        listener = lambda *args: statements.append(args[2])  # noqa: E731
        event.listen(db.bind.sync_engine, 'before_cursor_execute', listener)
        try:
            got = await get_subscription_by_user_id_in_session(db, user.id)
            tariff, owner = got.tariff, got.user  # заполнены, ленивой подгрузки нет
        finally:
            event.remove(db.bind.sync_engine, 'before_cursor_execute', listener)

        assert got.id == expected_id
        assert tariff is tariffs[0]
        assert owner is people[0]
        assert len(statements) == 1


async def test_subscription_without_tariff_gets_empty_relation(postgres_database):
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _person(db, 3002, [{'status': 'active', 'end_date': NOW + timedelta(days=3)}])
        db.expunge_all()
        people = (await db.execute(select(User))).scalars().all()

        got = await get_subscription_by_user_id_in_session(db, user.id)

        assert got.tariff is None
        assert got.user is people[0]


async def test_load_subscriptions_of_fills_collections_for_people_in_session(postgres_database):
    """Деактивация в синке: подписки поднимаются пачкой тем, кого нет в панели — без ленивой подгрузки."""
    from app.services.remnawave_service import RemnaWaveService

    async with postgres_session(postgres_database, TABLES) as db:
        first = await _person(
            db,
            4001,
            [
                {'status': 'expired', 'end_date': NOW - timedelta(days=2)},
                {'status': 'active', 'end_date': NOW + timedelta(days=9)},
            ],
        )
        second = await _person(db, 4002, [])
        db.expunge_all()
        people = {user.telegram_id: user for user in (await db.execute(select(User))).scalars().all()}

        await RemnaWaveService._load_subscriptions_of(db, list(people.values()), chunk_size=1)

        loaded = people[4001].subscriptions  # без запроса: иначе MissingGreenlet в async
        assert [subscription.status for subscription in loaded] == ['active', 'expired']  # order_by created_at desc
        assert people[4002].subscriptions == []
        assert {first.id, second.id} == {user.id for user in people.values()}
