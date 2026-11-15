"""Главная админки и «Кампании»: пакетные запросы дают те же числа.

* ``get_campaigns_statistics`` заменил цикл ``get_campaign_statistics`` по
  кампаниям (9 запросов на кампанию → 6 на все). Сверяем со старой одиночной
  функцией: пользователь в двух кампаниях, нереальные платежи, незавершённые
  оплаты, повторные конверсии, пустая и несуществующая кампания.
* ``get_server_statistics`` считал «серверы с подключениями» отдельным
  LIKE-запросом на каждый сервер, теперь — одним с EXISTS.
* ``_get_tariff_stats`` делал 5 COUNT на тариф, теперь — один GROUP BY.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.cabinet.routes import admin_stats
from app.database.crud.campaign import get_campaign_statistics, get_campaigns_statistics
from app.database.crud.server_squad import get_server_statistics
from app.database.crud.transaction import REAL_PAYMENT_METHODS
from app.database.models import (
    AdvertisingCampaign,
    AdvertisingCampaignRegistration,
    PaymentMethod,
    PromoGroup,
    ServerSquad,
    Subscription,
    SubscriptionConversion,
    SubscriptionServer,
    SubscriptionStatus,
    Tariff,
    Transaction,
    TransactionType,
    User,
    UserStatus,
    server_squad_promo_groups,
    tariff_promo_groups,
)
from app.utils.timezone import local_day_start
from tests.fixtures.sqlite_memory import memory_session


TABLES = (
    User.__table__,
    PromoGroup.__table__,
    Tariff.__table__,
    Subscription.__table__,
    Transaction.__table__,
    AdvertisingCampaign.__table__,
    AdvertisingCampaignRegistration.__table__,
    SubscriptionConversion.__table__,
    ServerSquad.__table__,
    SubscriptionServer.__table__,
    tariff_promo_groups,
    server_squad_promo_groups,
)

NOW = datetime.now(UTC)
GATEWAY = REAL_PAYMENT_METHODS[0]


def _user(n: int, **extra) -> User:
    return User(telegram_id=5000 + n, status=UserStatus.ACTIVE.value, language='ru', balance_kopeks=0, **extra)


def _sub(user: User, suffix: str, **extra) -> Subscription:
    values = {
        'status': SubscriptionStatus.ACTIVE.value,
        'start_date': NOW - timedelta(days=5),
        'end_date': NOW + timedelta(days=25),
        'traffic_limit_gb': 0,
        'device_limit': 1,
        'remnawave_short_id': f'r{user.id}{suffix}',
        'is_trial': False,
    }
    values.update(extra)
    return Subscription(user_id=user.id, **values)


def _tx(user: User, kind: TransactionType, amount: int, *, method=GATEWAY, completed=True, days_ago=1) -> Transaction:
    return Transaction(
        user_id=user.id,
        type=kind.value,
        amount_kopeks=amount,
        payment_method=method,
        is_completed=completed,
        created_at=NOW - timedelta(days=days_ago),
    )


async def _seed_campaigns(db) -> list[int]:
    campaigns = [
        AdvertisingCampaign(name=f'C{i}', start_parameter=f'c{i}', bonus_type='balance', is_active=True)
        for i in range(1, 5)
    ]
    db.add_all(campaigns)
    users = [_user(i, has_had_paid_subscription=i in (1, 3, 5)) for i in range(1, 7)]
    db.add_all(users)
    await db.flush()
    c1, c2, c3, c4 = campaigns  # c4 — без регистраций
    a, b, c, d, e, f = users

    def reg(campaign, user, bonus_type='balance', bonus=0, days_ago=3):
        return AdvertisingCampaignRegistration(
            campaign_id=campaign.id,
            user_id=user.id,
            bonus_type=bonus_type,
            balance_bonus_kopeks=bonus,
            created_at=NOW - timedelta(days=days_ago),
        )

    db.add_all(
        [
            reg(c1, a, bonus=1000),
            reg(c1, b, bonus_type='subscription', days_ago=1),
            reg(c1, f),
            reg(c2, a, bonus_type='subscription', bonus=500),  # a — в двух кампаниях
            reg(c2, c, days_ago=7),
            reg(c3, d),
            reg(c3, e, bonus_type='subscription'),
        ]
    )
    db.add_all(
        [
            _tx(a, TransactionType.DEPOSIT, 10000),
            _tx(a, TransactionType.DEPOSIT, 2000, method=PaymentMethod.MANUAL.value),  # не реальный шлюз
            _tx(a, TransactionType.SUBSCRIPTION_PAYMENT, -9900, days_ago=5),
            _tx(a, TransactionType.SUBSCRIPTION_PAYMENT, -4900, days_ago=2),
            _tx(b, TransactionType.DEPOSIT, 3000, completed=False),
            _tx(b, TransactionType.SUBSCRIPTION_PAYMENT, -1500, method=PaymentMethod.BALANCE.value),
            _tx(c, TransactionType.DEPOSIT, 7000),
            _tx(c, TransactionType.SUBSCRIPTION_PAYMENT, -7000, completed=False),
            _tx(d, TransactionType.SUBSCRIPTION_PAYMENT, -3000, days_ago=10),
            _tx(f, TransactionType.DEPOSIT, 500),
        ]
    )
    db.add_all(
        [
            _sub(a, 'a', is_trial=True, status=SubscriptionStatus.EXPIRED.value, end_date=NOW - timedelta(days=1)),
            _sub(a, 'b'),
            _sub(b, 'a', is_trial=True),
            _sub(c, 'a', is_trial=True),
            _sub(d, 'a', is_trial=True, status=SubscriptionStatus.EXPIRED.value),
            _sub(e, 'a'),
        ]
    )
    db.add_all(
        [
            # a: конверсия позже первой оплаты; c: две конверсии; e: конверсия без оплаты
            SubscriptionConversion(
                user_id=a.id, first_payment_amount_kopeks=4900, converted_at=NOW - timedelta(days=2)
            ),
            SubscriptionConversion(
                user_id=c.id, first_payment_amount_kopeks=1000, converted_at=NOW - timedelta(days=6)
            ),
            SubscriptionConversion(
                user_id=c.id, first_payment_amount_kopeks=2000, converted_at=NOW - timedelta(days=4)
            ),
            SubscriptionConversion(
                user_id=e.id, first_payment_amount_kopeks=None, converted_at=NOW - timedelta(days=1)
            ),
        ]
    )
    await db.commit()
    return [c1.id, c2.id, c3.id, c4.id]


async def test_bulk_campaign_statistics_equal_single(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        ids = await _seed_campaigns(db)
        missing_id = max(ids) + 100
        expected = {cid: await get_campaign_statistics(db, cid) for cid in [*ids, missing_id]}
        actual = await get_campaigns_statistics(db, [*ids, missing_id, ids[0]])

    assert actual == expected
    c1 = actual[ids[0]]
    assert c1['registrations'] == 3
    assert c1['total_revenue_kopeks'] == 10000 + 500  # реальные завершённые пополнения a и f
    assert actual[ids[3]]['registrations'] == 0


async def test_bulk_campaign_statistics_empty_input(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        assert await get_campaigns_statistics(db, []) == {}


async def test_servers_with_connections_single_query(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        squads = [
            ServerSquad(squad_uuid=f'sq-{i}', display_name=f'S{i}', is_available=i != 4, original_name=f'S{i}')
            for i in range(1, 6)
        ]
        u1, u2, u3 = _user(1), _user(2), _user(3)
        db.add_all([*squads, u1, u2, u3])
        await db.flush()
        db.add_all(
            [
                _sub(u1, 'a', connected_squads=['sq-1', 'sq-x']),
                _sub(u2, 'a', status=SubscriptionStatus.TRIAL.value, connected_squads=['sq-2']),
                # истёкшая не считается; sq-10 не должен засчитать sq-1
                _sub(u3, 'a', status=SubscriptionStatus.EXPIRED.value, connected_squads=['sq-3', 'sq-10']),
            ]
        )
        await db.commit()

        stats = await get_server_statistics(db)

    assert stats['total_servers'] == 5
    assert stats['available_servers'] == 4
    assert stats['servers_with_connections'] == 2


async def _tariff_stats_reference(db) -> list[dict]:
    """Прежний расчёт: пять отдельных COUNT на каждый тариф."""
    now = datetime.now(UTC)
    today_start = local_day_start(now)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    items = []
    for tariff in (await db.execute(select(Tariff).order_by(Tariff.display_order))).scalars().all():

        async def count(*conditions, _tariff_id=tariff.id) -> int:
            query = select(func.count(Subscription.id)).where(Subscription.tariff_id == _tariff_id, *conditions)
            return (await db.execute(query)).scalar() or 0

        active = Subscription.status == SubscriptionStatus.ACTIVE.value
        items.append(
            {
                'tariff_id': tariff.id,
                'tariff_name': tariff.name,
                'active_subscriptions': await count(active),
                'trial_subscriptions': await count(active, Subscription.is_trial == True),
                'purchased_today': await count(Subscription.created_at >= today_start, Subscription.is_trial == False),
                'purchased_week': await count(Subscription.created_at >= week_ago, Subscription.is_trial == False),
                'purchased_month': await count(Subscription.created_at >= month_ago, Subscription.is_trial == False),
            }
        )
    return items


async def test_tariff_stats_grouped_query_matches_per_tariff_counts(monkeypatch) -> None:
    async with memory_session(monkeypatch, TABLES) as db:
        tariffs = [Tariff(name=name, display_order=order) for order, name in enumerate(['B', 'A', 'Empty'])]
        users = [_user(i) for i in range(1, 9)]
        db.add_all([*tariffs, *users])
        await db.flush()
        tb, ta, _ = tariffs
        ages = [0, 0, 3, 10, 20, 40, 1, 0]
        rows = []
        for i, (u, age) in enumerate(zip(users, ages, strict=True)):
            rows.append(
                _sub(
                    u,
                    'a',
                    tariff_id=(tb if i % 2 else ta).id,
                    is_trial=i in (1, 6),
                    status=SubscriptionStatus.EXPIRED.value if i in (3, 4) else SubscriptionStatus.ACTIVE.value,
                    created_at=NOW - timedelta(days=age, minutes=1),
                )
            )
        rows.append(_sub(users[0], 'b', tariff_id=None))  # подписка без тарифа не считается
        db.add_all(rows)
        await db.commit()

        expected = await _tariff_stats_reference(db)
        stats = await admin_stats._get_tariff_stats(db)

    assert [item.model_dump() for item in stats.tariffs] == expected
    assert stats.total_tariff_subscriptions == sum(item['active_subscriptions'] for item in expected)
    assert expected[-1]['active_subscriptions'] == 0  # тариф без подписок — нули, а не пропуск
