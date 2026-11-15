"""Страница «Трафик»: лёгкие строки вместо ORM дают те же данные.

``_load_user_map`` раньше поднимал полные ORM-объекты ``User`` с подписками и
тарифами (selectinload) — ~24 тыс. пользователей, 50 запросов и ~2,7 с
гидратации на event loop на каждый запрос страницы. Теперь это один запрос по
нужным колонкам. Сторож сверяет: таблица, фильтры, сортировки, обогащение и
суммы трат совпадают с тем, что давала ORM-загрузка.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.cabinet.routes import admin_traffic
from app.cabinet.schemas.traffic import TrafficNodeInfo
from app.database.models import (
    PromoGroup,
    ServerSquad,
    Subscription,
    SubscriptionStatus,
    Tariff,
    Transaction,
    TransactionType,
    User,
    UserStatus,
    server_squad_promo_groups,
    tariff_promo_groups,
)
from tests.fixtures.sqlite_memory import memory_session


TABLES = (
    User.__table__,
    Subscription.__table__,
    Tariff.__table__,
    Transaction.__table__,
    PromoGroup.__table__,
    ServerSquad.__table__,
    tariff_promo_groups,
    server_squad_promo_groups,
)

NOW = datetime.now(UTC)
NODES = [
    TrafficNodeInfo(node_uuid='node-a', node_name='A', country_code='DE'),
    TrafficNodeInfo(node_uuid='node-b', node_name='B', country_code='NL'),
]


async def _seed(db) -> dict[int, dict[str, int]]:
    standard = Tariff(name='Стандарт', display_order=1)
    ultima = Tariff(name='ULTIMA', display_order=2)
    db.add_all([standard, ultima])
    await db.flush()

    def user(n: int, **extra) -> User:
        return User(telegram_id=1000 + n, status=UserStatus.ACTIVE.value, language='ru', balance_kopeks=0, **extra)

    users = [
        user(1, username='alice', first_name='Alice', last_name='Doe', remnawave_id=501),
        user(2, username='bob', remnawave_id=502),
        user(3, email='carol@mail.example', remnawave_id=503),
        user(4, first_name='Dan', remnawave_id=504),  # без подписки
        user(5, username='eve', remnawave_id=505),
        user(6, username='no_panel'),  # без panel id — в таблицу не попадает
    ]
    db.add_all(users)
    await db.flush()

    def sub(u: User, suffix: str, **extra) -> Subscription:
        values = {
            'status': SubscriptionStatus.ACTIVE.value,
            'start_date': NOW - timedelta(days=10),
            'end_date': NOW + timedelta(days=20),
            'traffic_limit_gb': 100,
            'device_limit': 3,
            'remnawave_short_id': f's{u.id}{suffix}',
        }
        values.update(extra)
        return Subscription(user_id=u.id, **values)

    db.add_all(
        [
            sub(users[0], 'a', tariff_id=standard.id, created_at=NOW - timedelta(days=30)),
            # Две подписки: активная новее, истёкшая старше — «основной» должна стать активная.
            sub(users[1], 'a', tariff_id=ultima.id, created_at=NOW - timedelta(days=2)),
            sub(
                users[1],
                'b',
                tariff_id=standard.id,
                status=SubscriptionStatus.EXPIRED.value,
                end_date=NOW - timedelta(days=1),
                created_at=NOW - timedelta(days=40),
            ),
            sub(users[2], 'a', status=SubscriptionStatus.TRIAL.value, traffic_limit_gb=0, device_limit=None),
            # Статус active, но срок вышел — actual_status = expired.
            sub(users[4], 'a', tariff_id=ultima.id, end_date=NOW - timedelta(hours=1)),
            sub(users[5], 'a', tariff_id=standard.id),
        ]
    )

    def payment(u: User, amount: int, *, kind=TransactionType.SUBSCRIPTION_PAYMENT, completed=True) -> Transaction:
        return Transaction(
            user_id=u.id,
            type=kind.value,
            amount_kopeks=amount,
            payment_method='yookassa',
            is_completed=completed,
        )

    db.add_all(
        [
            payment(users[0], -15000),
            payment(users[0], -5000),
            payment(users[1], -30000),
            payment(users[1], 99999, kind=TransactionType.DEPOSIT),  # не оплата подписки
            payment(users[2], -7000, completed=False),  # не завершена
            payment(users[5], -1000),  # без panel id
        ]
    )
    await db.commit()

    return {501: {'node-a': 300, 'node-b': 100}, 502: {'node-b': 900}, 505: {'node-a': 50}, 999: {'node-a': 7}}


async def _orm_user_map(db) -> dict[int, User]:
    """Прежняя загрузка — эталон."""
    result = await db.execute(
        select(User)
        .where(User.remnawave_id.isnot(None))
        .options(selectinload(User.subscriptions).selectinload(Subscription.tariff))
    )
    return {u.remnawave_id: u for u in result.scalars().all() if u.remnawave_id}


def _dump(rows) -> list[dict]:
    return [row.to_item().model_dump() for row in rows]


@pytest.mark.parametrize(
    'kwargs',
    [
        {},
        {'sort_by': 'full_name', 'sort_desc': False},
        {'sort_by': 'tariff_name'},
        {'sort_by': 'device_limit'},
        {'sort_by': 'traffic_limit_gb', 'sort_desc': False},
        {'sort_by': 'node_node-b'},
        {'search': 'mail.example'},
        {'tariff_filter': {'ULTIMA'}},
        {'status_filter': {'active', 'trial'}},
        {'status_filter': {'expired'}},
        {'node_filter': {'node-a'}},
    ],
)
async def test_light_user_map_gives_same_table_as_orm(monkeypatch, kwargs) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        traffic = await _seed(db)
        orm_map = await _orm_user_map(db)
        light_map = await admin_traffic._load_user_map(db)

    assert sorted(light_map) == sorted(orm_map) == [501, 502, 503, 504, 505]
    expected = _dump(admin_traffic._build_traffic_items(traffic, orm_map, NODES, **kwargs))
    actual = _dump(admin_traffic._build_traffic_items(traffic, light_map, NODES, **kwargs))
    assert actual == expected
    assert expected, 'выборка не должна быть пустой — иначе сравнивать нечего'


async def test_light_rows_keep_statuses_and_primary_subscription(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        traffic = await _seed(db)
        light_map = await admin_traffic._load_user_map(db)

    rows = {row.user_id: row for row in admin_traffic._build_traffic_items(traffic, light_map, NODES)}
    bob = light_map[502]
    assert [s.status for s in bob.subscriptions] == ['active', 'expired']  # created_at по убыванию
    bob_item = rows[bob.id].to_item()
    assert bob_item.tariff_name == 'ULTIMA'
    assert bob_item.subscription_status == 'active'
    assert [s.status for s in bob_item.subscriptions] == ['active', 'expired']
    assert rows[light_map[505].id].subscription_status == 'expired'
    assert rows[light_map[503].id].to_item().device_limit == 1
    assert rows[light_map[504].id].to_item().subscriptions == []


async def test_enrichment_and_spending_match_orm(monkeypatch) -> None:
    class _NoPanel:
        is_configured = False

    monkeypatch.setattr(admin_traffic, 'RemnaWaveService', _NoPanel)
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        orm_map = await _orm_user_map(db)
        light_map = await admin_traffic._load_user_map(db)
        expected, _ = await admin_traffic._build_enrichment(db, orm_map)
        actual, _ = await admin_traffic._build_enrichment(db, light_map)
        spending = await admin_traffic._get_bulk_spending(db, [u.id for u in light_map.values()])

    assert {k: v.model_dump() for k, v in actual.items()} == {k: v.model_dump() for k, v in expected.items()}
    alice, bob, carol = light_map[501], light_map[502], light_map[503]
    # Только завершённые оплаты подписок и только запрошенные люди (у no_panel тоже есть оплата).
    assert spending == {alice.id: 20000, bob.id: 30000}
    assert carol.id not in spending


async def test_concurrent_requests_share_one_user_map_load(monkeypatch) -> None:
    calls = 0
    release = asyncio.Event()

    async def slow_load(db):
        nonlocal calls
        calls += 1
        await release.wait()
        return {1: f'map-{calls}'}

    monkeypatch.setattr(admin_traffic, '_load_user_map', slow_load)
    tasks = [asyncio.create_task(admin_traffic._get_user_map(None)) for _ in range(4)]
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)

    assert calls == 1
    assert all(r is results[0] for r in results)
    # Готовый результат не запоминается: следующий запрос грузит свежие данные.
    assert await admin_traffic._get_user_map(None) == {1: 'map-2'}


async def test_waiter_loads_itself_when_shared_load_fails(monkeypatch) -> None:
    attempts = 0
    started = asyncio.Event()
    fail_now = asyncio.Event()

    async def flaky_load(db):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await fail_now.wait()
            raise RuntimeError('db hiccup')
        return {'ok': db}

    monkeypatch.setattr(admin_traffic, '_load_user_map', flaky_load)
    leader = asyncio.create_task(admin_traffic._get_user_map('leader-db'))
    await started.wait()
    follower = asyncio.create_task(admin_traffic._get_user_map('follower-db'))
    await asyncio.sleep(0)  # второй запрос уже ждёт общую загрузку
    assert attempts == 1
    fail_now.set()

    with pytest.raises(RuntimeError, match='db hiccup'):
        await leader
    assert await follower == {'ok': 'follower-db'}
    assert admin_traffic._user_map_inflight is None
