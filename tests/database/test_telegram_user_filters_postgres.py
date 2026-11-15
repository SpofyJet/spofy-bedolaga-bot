"""TG-053: состав traffic_low в списке пользователей кабинета на PostgreSQL."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.cabinet.routes import admin_users
from app.database.models import Subscription, User
from app.services import panel_online
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres
TABLES = [User.__table__]


@asynccontextmanager
async def _client(db, monkeypatch):
    app = FastAPI()
    app.include_router(admin_users.router, prefix='/cabinet')

    async def session():
        yield db

    app.dependency_overrides[admin_users.get_cabinet_db] = session
    permission = inspect.signature(admin_users.list_users).parameters['admin'].default.dependency
    app.dependency_overrides[permission] = lambda: None
    monkeypatch.setattr(panel_online, 'get_online_snapshot', AsyncMock(return_value=None))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield client


async def _seed_traffic(db):
    now = datetime.now(UTC)
    specs = {
        'boundary': [('active', 80, 100)],
        'below': [('active', 79.99, 100)],
        'above': [('active', 80.01, 100)],
        'limited': [('limited', 100, 100)],
        'trial': [('trial', 8, 10)],
        'active_trial': [('active', 8, 10)],
        'unlimited': [('active', 1000, 0)],
        'empty': [('active', 0, 600)],
        'expired': [('expired', 100, 100)],
        'disabled': [('disabled', 100, 100)],
        'multi': [('active', 0, 600), ('active', 90, 100), ('limited', 200, 200)],
        'none': [],
    }
    for index, (name, subs) in enumerate(specs.items(), 1):
        user = User(telegram_id=index, username=name, first_name=name, status='active', language='ru')
        db.add(user)
        await db.flush()
        for sub_index, (status, used, limit) in enumerate(subs):
            db.add(
                Subscription(
                    user_id=user.id,
                    status=status,
                    is_trial=name in {'trial', 'active_trial'},
                    start_date=now - timedelta(days=10),
                    end_date=now + timedelta(days=1 + sub_index),
                    traffic_used_gb=used,
                    traffic_limit_gb=limit,
                    device_limit=1,
                    remnawave_short_id=f'masked-{index}-{sub_index}',
                )
            )
    await db.commit()
    db.expunge_all()


@pytest.mark.parametrize('sort', list(admin_users.SortByEnum))
@pytest.mark.parametrize('direction', ['asc', 'desc'])
@pytest.mark.parametrize('threshold', [80, 100])
async def test_traffic_filter_returns_exact_people_for_every_sort(
    postgres_database, monkeypatch, sort, direction, threshold
):
    expected = {'limited', 'multi'}
    if threshold == 80:
        expected |= {'boundary', 'above', 'trial', 'active_trial'}
    async with postgres_session(postgres_database, TABLES) as db:
        await _seed_traffic(db)
        async with _client(db, monkeypatch) as client:
            params = {'traffic_used_percent_min': threshold, 'sort_by': sort.value, 'sort_order': direction}
            response = await client.get('/cabinet/admin/users', params=params)
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload['total'] == len(expected)
            assert {item['username'] for item in payload['users']} == expected
            assert len(payload['users']) == len(expected)
            for item in payload['users']:
                assert item['traffic_limit_gb'] > 0
                assert item['traffic_used_gb'] >= item['traffic_limit_gb'] * threshold / 100
            multi = next(item for item in payload['users'] if item['username'] == 'multi')
            assert len(multi['subscriptions']) == 3

            # LIMIT/OFFSET применяется к людям, а не к строкам JOIN подписок.
            paged = []
            for offset in range(0, len(expected) + 1, 2):
                response = await client.get('/cabinet/admin/users', params={**params, 'limit': 2, 'offset': offset})
                assert response.status_code == 200, response.text
                page = response.json()
                assert page['total'] == len(expected)
                paged.extend(item['id'] for item in page['users'])
            assert paged == [item['id'] for item in payload['users']]


@pytest.mark.parametrize('status', ['active', 'trial', 'limited'])
async def test_traffic_filter_excludes_overdue_subscription_before_status_update(
    postgres_database, monkeypatch, status
):
    async with postgres_session(postgres_database, TABLES) as db:
        user = User(telegram_id=1, username='masked-overdue', first_name='masked-overdue', language='ru')
        db.add(user)
        await db.flush()
        db.add(
            Subscription(
                user_id=user.id,
                status=status,
                is_trial=status == 'trial',
                start_date=datetime.now(UTC) - timedelta(days=10),
                end_date=datetime.now(UTC) - timedelta(days=1),
                traffic_used_gb=100,
                traffic_limit_gb=100,
                device_limit=1,
                remnawave_short_id='masked-overdue',
            )
        )
        await db.commit()
        db.expunge_all()
        async with _client(db, monkeypatch) as client:
            response = await client.get('/cabinet/admin/users', params={'traffic_used_percent_min': 80})
            assert response.status_code == 200, response.text
            assert response.json()['total'] == 0
            assert response.json()['users'] == []


@pytest.mark.parametrize('stale_status', ['expired', 'disabled', 'active', 'trial', 'limited'])
async def test_traffic_row_ignores_stale_subscription_with_higher_usage(postgres_database, monkeypatch, stale_status):
    async with postgres_session(postgres_database, TABLES) as db:
        await _seed_traffic(db)
        # "multi" имеет живой LIMITED 200/200; старый тариф 300/100 не должен
        # вытеснить его в строке, если сам не проходит условия traffic_low.
        db.add(
            Subscription(
                user_id=11,
                status=stale_status,
                is_trial=stale_status == 'trial',
                start_date=datetime.now(UTC) - timedelta(days=10),
                end_date=datetime.now(UTC) + timedelta(days=1 if stale_status in {'expired', 'disabled'} else -1),
                traffic_used_gb=300,
                traffic_limit_gb=100,
                device_limit=1,
                remnawave_short_id='masked-stale',
            )
        )
        await db.commit()
        db.expunge_all()
        async with _client(db, monkeypatch) as client:
            response = await client.get(
                '/cabinet/admin/users', params={'traffic_used_percent_min': 80, 'search': 'multi'}
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload['total'] == 1
            assert len(payload['users']) == 1
            row = payload['users'][0]
            assert row['traffic_used_gb'] == 200
            assert row['traffic_limit_gb'] == 200
            assert row['subscription_status'] == 'limited'
            assert len(row['subscriptions']) == 4
