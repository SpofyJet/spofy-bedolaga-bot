"""Panel imports preserve exact identities and do not invent billing choices."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import (
    Base,
    Subscription,
    Transaction,
    User,
)
from app.services.remnawave_service import RemnaWaveService
from tests.fixtures.postgres_db import (
    postgres_session,
)


pytestmark = pytest.mark.postgres
TABLES = list(Base.metadata.sorted_tables)
NOW = datetime.now(UTC)
END = NOW + timedelta(days=30)
GIB = 1024**3


def account(*, tag=None, panel_id=9001, short='shared-short', username='account_local10'):
    return SimpleNamespace(
        id=panel_id,
        short_uuid=short,
        username=username,
        status=SimpleNamespace(value='ACTIVE'),
        telegram_id=101,
        email=None,
        expire_at=END,
        used_traffic_bytes=5 * GIB,
        traffic_limit_bytes=120 * GIB,
        hwid_device_limit=5,
        subscription_url=f'https://subscription.example/{short}',
        happ_crypto_link='',
        active_internal_squads=[{'uuid': 'test-squad'}],
        tag=tag,
    )


def service(monkeypatch, accounts):
    monkeypatch.setattr(settings, 'TRIAL_USER_TAG', 'TRIAL')
    api = SimpleNamespace(
        get_all_users_page_stream=AsyncMock(return_value={'users': accounts, 'hasMore': False, 'nextCursor': None}),
        get_user_by_id=AsyncMock(side_effect=lambda panel_id: next((a for a in accounts if a.id == panel_id), None)),
    )

    @asynccontextmanager
    async def client(self):
        yield api

    svc = RemnaWaveService()
    monkeypatch.setattr(svc, 'get_api_client', lambda: client(svc))
    svc.test_api = api
    return svc


async def seed(db, *, user_panel_id=None):
    user = User(id=1, telegram_id=101, status='active', language='ru', remnawave_id=user_panel_id)
    db.add(user)
    await db.commit()
    return user


@pytest.mark.parametrize(
    ('configured_tag', 'panel_tag', 'trial'),
    [
        ('TRIAL', 'TRIAL', True),
        ('TRY', 'TRY', True),
        (None, 'TRIAL', True),
        (None, None, False),
        ('TRIAL', 'PAID', False),
        ('TRIAL', None, False),
        ('TRY', 'TRIAL', False),
    ],
)
async def test_import_reads_configured_trial_marker(postgres_database, monkeypatch, configured_tag, panel_tag, trial):
    svc = service(monkeypatch, [account(tag=panel_tag)])
    monkeypatch.setattr(settings, 'TRIAL_USER_TAG', configured_tag)
    async with postgres_session(postgres_database, TABLES) as db:
        await seed(db)
        stats = await svc.sync_users_from_panel(db, 'all')
        rows = list((await db.scalars(select(Subscription))).all())
        assert stats['errors'] == 0
        assert len(rows) == 1
        assert rows[0].is_trial is trial
        assert rows[0].end_date == END
        assert rows[0].device_limit == 5
        assert (await db.get(User, 1)).balance_kopeks == 0
        assert list((await db.scalars(select(Transaction))).all()) == []
