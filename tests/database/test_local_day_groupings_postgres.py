"""Дым: каждая группировка по локальному дню исполняется на настоящем PostgreSQL (#3136).

Прод 2026-09-12: статистика продаж в кабинете падала с «column must appear in
the GROUP BY clause» — CI это не поймал, потому что единственный тест на
PostgreSQL переиспользовал одно выражение, а боевые запросы строят его
отдельно для SELECT и GROUP BY. Здесь вызывается каждый потребитель
``local_date_expr`` (список — из графа вызовов) на полной схеме: пустые
таблицы достаточно, чтобы PostgreSQL разобрал и выполнил запросы.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cabinet.routes import admin_sales_stats
from tests.fixtures.local_day import (  # noqa: F401
    reset_local_timezone_cache,
    use_timezone,
)
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres

ADMIN = SimpleNamespace(id=1, username='admin')

SALES_ROUTES = [
    admin_sales_stats.get_sales_summary,
    admin_sales_stats.get_trials_stats,
    admin_sales_stats.get_sales_stats,
    admin_sales_stats.get_renewals_stats,
    admin_sales_stats.get_addons_stats,
    admin_sales_stats.get_deposits_stats,
    admin_sales_stats.get_payment_health,
]


@pytest.mark.asyncio
@pytest.mark.parametrize('route', SALES_ROUTES, ids=lambda route: route.__name__)
async def test_sales_stats_route_groups_by_local_day(route, postgres_database, monkeypatch, reset_local_timezone_cache):
    use_timezone(monkeypatch, 'Europe/Moscow')

    async with postgres_session(postgres_database) as db:
        await route(days=30, start_date=None, end_date=None, admin=ADMIN, db=db)


@pytest.mark.asyncio
async def test_sales_stats_custom_period_groups_by_local_day(
    postgres_database, monkeypatch, reset_local_timezone_cache
):
    use_timezone(monkeypatch, 'Europe/Moscow')

    async with postgres_session(postgres_database) as db:
        await admin_sales_stats.get_sales_stats(
            days=None, start_date='2026-09-01', end_date='2026-09-10', admin=ADMIN, db=db
        )
