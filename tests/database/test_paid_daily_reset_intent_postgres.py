"""TG030: paid reset delivery survives failure without replaying destructive POSTs."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.database.models import (
    Base,
    PaidTrafficResetIntent,
    Subscription,
    Transaction,
    User,
)
from app.services import (
    paid_traffic_reset_service as resets,
    subscription_auto_purchase_service as auto,
    subscription_renewal_service as renewal,
    subscription_service as sync_module,
)
from app.services.daily_subscription_service import DailySubscriptionService
from tests.fixtures.postgres_db import postgres_engine
from tests.services.test_daily_charge_traffic_reset import _subscription, _tariff, _user
from tests.services.test_daily_topup_resume_traffic_reset import _rows


pytestmark = pytest.mark.postgres
GIB = 1024**3


class Panel:
    def __init__(self):
        self.user = SimpleNamespace(
            id=9001,
            short_uuid='masked-panel',
            status='ACTIVE',
            last_traffic_reset_at=datetime.now(UTC) - timedelta(days=2),
            last_traffic_reset_at_known=True,
            user_traffic=object(),
            used_traffic_bytes=90 * GIB,
            traffic_limit_bytes=100 * GIB,
        )
        self.reset_calls = 0
        self.enable_calls = 0
        self.canonical_calls = []
        self.failure = None
        self.enable_failure = False
        self.before_reset = None

    async def get_user_by_id(self, panel_id):
        assert panel_id == 9001
        return self.user

    async def reset_user_traffic(self, panel_id, *, enrich=True):
        assert panel_id == 9001 and enrich is False
        self.reset_calls += 1
        if self.before_reset:
            await self.before_reset()
        if self.failure in ('timeout_no_apply', 'cancel'):
            if self.failure == 'cancel':
                import asyncio

                raise asyncio.CancelledError
            raise TimeoutError('test reset response unknown')
        self.user.last_traffic_reset_at = datetime.now(UTC)
        self.user.used_traffic_bytes = 0
        if self.failure == 'lost_ack':
            self.user.used_traffic_bytes = 7 * GIB
            raise TimeoutError('test reset applied but response lost')
        return self.user

    async def enable_user(self, panel_id):
        self.enable_calls += 1
        if self.enable_failure:
            raise TimeoutError('test enable failed')
        self.user.status = 'ACTIVE'
        return self.user


@pytest.fixture
def panel(monkeypatch):
    panel = Panel()
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', True)
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True)
    monkeypatch.setattr(settings, 'DAILY_SUBSCRIPTIONS_ENABLED', True)
    monkeypatch.setattr(renewal, 'with_admin_notification_service', AsyncMock())

    class Service:
        is_configured = True

        @asynccontextmanager
        async def get_api_client(self):
            yield panel

        async def update_remnawave_user(self, db, sub, **kwargs):
            panel.canonical_calls.append(kwargs)
            assert kwargs['reset_traffic'] is False
            if panel.failure == 'canonical_none':
                return None
            if panel.failure == 'canonical_raise':
                raise TimeoutError('test canonical failure')
            return panel.user

        create_remnawave_user = update_remnawave_user
        sync_remnawave_user = update_remnawave_user

    monkeypatch.setattr(sync_module, 'SubscriptionService', Service)
    monkeypatch.setattr(auto, 'SubscriptionService', Service)
    return panel


async def charge(db, flow, *, strategy='NO_RESET'):
    db.add_all(
        [_user(), _tariff(strategy), _subscription()]
        if flow == 'scheduled'
        else _rows(traffic_reset_mode=strategy, status='disabled')
    )
    await db.commit()
    svc = DailySubscriptionService()
    sub = await svc._reload_daily_subscription(db, 10)
    result = (
        await svc._process_single_charge(db, sub)
        if flow == 'scheduled'
        else await auto.try_resume_disabled_daily_after_topup(db, await db.get(User, 1))
    )
    assert result == ('charged' if flow == 'scheduled' else True)
    return (await db.scalars(select(PaidTrafficResetIntent))).one_or_none()


async def due(maker):
    async with maker() as db:
        await db.execute(update(PaidTrafficResetIntent).values(next_check_at=None))
        await db.commit()


@pytest.mark.parametrize('flow', ['scheduled', 'topup'])
@pytest.mark.parametrize('failure', ['canonical_none', 'canonical_raise', 'lost_ack', 'timeout_no_apply', None])
async def test_delivery_failure_and_restart(postgres_database, monkeypatch, panel, flow, failure):
    panel.failure = failure
    async with postgres_engine(postgres_database, list(Base.metadata.sorted_tables)) as engine:
        maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with maker() as db:
            intent = await charge(db, flow)
            await db.refresh(intent)
            assert (await db.get(User, 1)).balance_kopeks == 99000
            assert len(list((await db.scalars(select(Transaction))).all())) == 1
            expected = (
                'pending' if failure and failure.startswith('canonical') else 'attempted' if failure else 'confirmed'
            )
            assert intent.state == expected
            await db.refresh(await db.get(Subscription, 10))
            assert (await db.get(Subscription, 10)).traffic_used_gb == (0 if failure is None else 90)
        panel.failure = None
        await due(maker)
        # A new invocation has no in-memory intent/queue state.
        await resets.process_pending_daily_resets(maker)
        async with maker() as db:
            intent = (await db.scalars(select(PaidTrafficResetIntent))).one()
            assert (await db.get(User, 1)).balance_kopeks == 99000
            assert len(list((await db.scalars(select(Transaction))).all())) == 1
            if failure == 'timeout_no_apply':
                assert intent.state == 'attempted'
                assert (await db.get(Subscription, 10)).traffic_used_gb == 90
            else:
                assert intent.state == 'confirmed'
                assert (await db.get(Subscription, 10)).traffic_used_gb == (7 if failure == 'lost_ack' else 0)
            assert panel.reset_calls == 1


async def test_foreign_subscription_owner_prevents_reset(postgres_database, monkeypatch, panel):
    panel.failure = 'canonical_none'
    async with postgres_engine(postgres_database, list(Base.metadata.sorted_tables)) as engine:
        maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with maker() as db:
            intent_id = (await charge(db, 'scheduled')).id
            (await db.get(Subscription, 10)).remnawave_id = None
            db.add(User(id=2, status='active'))
            await db.flush()
            db.add(
                Subscription(
                    id=20,
                    user_id=2,
                    status='active',
                    is_trial=False,
                    remnawave_id=9001,
                    end_date=datetime.now(UTC) + timedelta(days=1),
                )
            )
            await db.commit()
            assert not await resets.deliver_daily_reset(db, intent_id)
            await db.refresh(await db.get(PaidTrafficResetIntent, intent_id))
            assert (await db.get(PaidTrafficResetIntent, intent_id)).last_error == 'panel_account_owned_elsewhere'
        assert panel.reset_calls == 0
