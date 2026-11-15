"""Committed renewal survives lost in-memory retries and stale panel events."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.database.models import Base, Subscription, Transaction, User
from app.external.remnawave_api import RemnaWaveAPI, RemnaWaveAPIError
from app.services import remnawave_retry_queue as retry
from app.services.remnawave_webhook_service import RemnaWaveWebhookService
from app.services.subscription_service import SubscriptionService
from tests.database.test_renewal_survives_stale_panel_snapshot_postgres import (
    BALANCE,
    PRICE,
    _PanelPatchFails,
    _renew_from_cabinet,
    _seed,
)
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres


class Panel(RemnaWaveAPI):
    def __init__(self, now, missing=False):
        super().__init__(base_url='https://panel.example', api_key='test')
        self.missing = missing
        self.patches = []
        self.device_reads = []
        self.creates = 0
        self.traffic_used = 17
        self.traffic_resets = 0
        self.hwid_failures = 0
        self.account = dict(
            id=9001,
            shortUuid='test-short',
            username='test-user',
            status='EXPIRED',
            expireAt=(now - timedelta(days=1)).isoformat(),
            createdAt=now.isoformat(),
            updatedAt=now.isoformat(),
            telegramId=101,
            subscriptionUrl='https://vpn.example/sub/test',
            hwidDeviceLimit=1,
        )

    async def get_user_by_id(self, user_id):
        if user_id == 9003:
            return self._parse_user(self.new_account)
        assert user_id == 9001
        return None if self.missing else self._parse_user(self.account)

    async def create_user(self, **kwargs):
        self.creates += 1
        self.create_kwargs = kwargs.copy()
        self.new_account = dict(
            self.account,
            id=9003,
            expireAt=kwargs['expire_at'].isoformat(),
            subscriptionUrl='https://vpn.example/sub/recreated',
            status='ACTIVE',
        )
        return self._parse_user(self.new_account)

    async def get_user_by_short_uuid(self, short_uuid):
        return None

    async def find_users_by_telegram_id(self, telegram_id):
        return []

    async def get_user_by_username(self, username):
        return None

    async def enrich_user_with_happ_link(self, user):
        return user

    async def _make_request(self, method, path, data=None, **kwargs):
        if (method, path) == ('GET', '/api/hwid/devices/9001'):
            assert not self.missing
            self.device_reads.append(9001)
            if self.hwid_failures:
                self.hwid_failures -= 1
                raise RemnaWaveAPIError('test HWID service unavailable', 503)
            return {'response': {'total': 1, 'devices': [{'userId': 9001, 'hwid': 'test-phone'}]}}
        if (method, path) == ('PATCH', '/api/users'):
            assert data['id'] == 9001
            if self.missing:
                raise RemnaWaveAPIError('User not found', 404, {'errorCode': 'A025'})
            self.patches.append(data.copy())
            self.account.update(data)
            return {'response': self.account}
        assert method == 'POST' and path in [
            '/api/users/9001/actions/reset-traffic',
            '/api/users/9003/actions/reset-traffic',
        ]
        self.traffic_used = 0
        self.traffic_resets += 1
        return {'response': self.account if '9001' in path else self.new_account}


@pytest.fixture(autouse=True)
def isolated_renewal(monkeypatch):
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', False)
    monkeypatch.setattr(settings, 'RESET_DEVICES_ON_RENEWAL', False)
    monkeypatch.setattr(retry, 'remnawave_retry_queue', retry.RemnaWaveRetryQueue())
    _PanelPatchFails.calls.clear()
    yield
    _PanelPatchFails.calls.clear()


@pytest.mark.parametrize('event', ['user.expired', 'user.modified'])
@pytest.mark.parametrize('age_hours', [1, 73])
async def test_paid_expiry_survives_restart_and_stale_event(postgres_database, monkeypatch, event, age_hours):
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user, subscription, old_end = await _seed(db, datetime.now(UTC) - timedelta(days=3))
        user_id, subscription_id = user.id, subscription.id
        await _renew_from_cabinet(db, user, subscription, monkeypatch)
        await db.refresh(subscription)
        paid_until = subscription.end_date
        assert paid_until > datetime.now(UTC) + timedelta(days=29)
        assert retry.remnawave_retry_queue.pending_count == 1
        # The old 48-hour heuristic must not be the only persistent evidence.
        await db.execute(update(Transaction).values(created_at=datetime.now(UTC) - timedelta(hours=age_hours)))
        await db.commit()
        db.expunge_all()
        monkeypatch.setattr(retry, 'remnawave_retry_queue', retry.RemnaWaveRetryQueue())
        user = await db.get(User, user_id)
        subscription = await db.get(Subscription, subscription_id)
        service = RemnaWaveWebhookService(AsyncMock())
        monkeypatch.setattr(service, '_notify_user', AsyncMock())
        await service._process_user_event(
            db,
            event,
            {
                'id': 555,
                'telegramId': 1,
                'status': 'EXPIRED',
                'expireAt': old_end.isoformat(),
            },
            service._handle_user_expired if event == 'user.expired' else service._handle_user_modified,
        )
        await db.refresh(subscription)
        await db.refresh(user)
        assert subscription.end_date == paid_until
        assert subscription.status == 'active'
        assert user.balance_kopeks == BALANCE - PRICE
        transactions = list(await db.scalars(select(Transaction).where(Transaction.type == 'subscription_payment')))
        assert len(transactions) == 1


async def test_restart_recovers_expiry_until_panel_confirms_without_charging_again(postgres_database, monkeypatch):
    monkeypatch.setattr(settings, 'REMNAWAVE_API_URL', 'https://panel.example')
    monkeypatch.setattr(settings, 'REMNAWAVE_API_KEY', 'test')
    panel = Panel(datetime.now(UTC))
    panel.account['telegramId'] = 1

    @asynccontextmanager
    async def client(self):
        yield panel

    monkeypatch.setattr(SubscriptionService, 'get_api_client', client)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user, subscription, _ = await _seed(db, datetime.now(UTC))
        await _renew_from_cabinet(db, user, subscription, monkeypatch)
        await db.refresh(subscription)
        target = subscription.end_date
        user.remnawave_id = subscription.remnawave_id = 9001
        await db.commit()
        monkeypatch.setattr(retry, 'AsyncSessionLocal', async_sessionmaker(db.bind, expire_on_commit=False))
        panel.hwid_failures = 2
        for _ in range(2):
            # Each new worker has an empty memory queue and a one-attempt budget.
            queue = retry.RemnaWaveRetryQueue(max_retries=1)
            monkeypatch.setattr(retry, 'remnawave_retry_queue', queue)
            await queue.process_pending()
        assert len(panel.patches) == 2, 'Committed expiry must repopulate retries even after exhaustion/restart'
        queue = retry.RemnaWaveRetryQueue(max_retries=1)
        monkeypatch.setattr(retry, 'remnawave_retry_queue', queue)
        await queue.process_pending()
        await db.refresh(subscription)
        await db.refresh(user)
        assert subscription.pending_panel_expire_at is None
        assert panel._parse_user(panel.account).expire_at == target
        assert user.balance_kopeks == BALANCE - PRICE
        assert len(list(await db.scalars(select(Transaction).where(Transaction.type == 'subscription_payment')))) == 1
        await db.commit()
        await queue.process_pending()
        assert len(panel.patches) == 3, 'Acknowledged expiry must not produce endless retries'


@pytest.mark.parametrize('concurrent_change', ['renewal', 'admin-shortening', 'none'])
async def test_old_panel_ack_cannot_clear_newer_local_intent(postgres_database, concurrent_change):
    from types import SimpleNamespace

    from app.services.panel_sync.expiry_intent import acknowledge_pending_expiry

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        _, subscription, _ = await _seed(db, datetime.now(UTC))
        original = subscription.end_date
        subscription.pending_panel_expire_at = original
        await db.commit()
        sessions = async_sessionmaker(db.bind, expire_on_commit=False)
        async with sessions() as writer:
            stale = await writer.get(Subscription, subscription.id)
            if concurrent_change != 'none':
                delta = timedelta(days=30 if concurrent_change == 'renewal' else -1)
                subscription.end_date = original + delta
                subscription.pending_panel_expire_at = subscription.end_date
                await db.commit()
            await acknowledge_pending_expiry(writer, stale, SimpleNamespace(expire_at=original))
            await writer.commit()
        await db.refresh(subscription)
        if concurrent_change == 'none':
            assert subscription.pending_panel_expire_at is None
        else:
            assert subscription.pending_panel_expire_at == original + delta
            assert subscription.end_date == original + delta


@pytest.mark.parametrize('state', ['blocked', 'paused', 'grace', 'expired', 'obsolete'])
async def test_recovery_does_not_revive_ineligible_subscriptions(postgres_database, monkeypatch, state):
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user, subscription, _ = await _seed(db, datetime.now(UTC))
        subscription.pending_panel_expire_at = subscription.end_date
        if state == 'blocked':
            user.status = 'blocked'
        elif state == 'paused':
            subscription.is_daily_paused = True
        elif state == 'grace':
            subscription.grace_session_open = True
        elif state == 'expired':
            subscription.end_date = subscription.pending_panel_expire_at = datetime.now(UTC) - timedelta(days=1)
        elif state == 'obsolete':
            subscription.end_date -= timedelta(days=1)
        await db.commit()
        monkeypatch.setattr(retry, 'AsyncSessionLocal', async_sessionmaker(db.bind, expire_on_commit=False))
        create = AsyncMock(side_effect=AssertionError('Ineligible subscription must not be written'))
        monkeypatch.setattr(SubscriptionService, 'create_remnawave_user', create)
        await retry.RemnaWaveRetryQueue().process_pending()
        create.assert_not_called()


@pytest.mark.parametrize('confirmed', [False, True])
async def test_bonus_extension_pending_vs_confirmed_panel_change(postgres_database, monkeypatch, confirmed):
    from types import SimpleNamespace

    from app.services.panel_sync.expiry_intent import acknowledge_pending_expiry

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user, subscription, original = await _seed(db, datetime.now(UTC))
        subscription.extend_subscription(30)  # bonus days: no payment transaction
        target = subscription.end_date
        await db.commit()
        if confirmed:
            await acknowledge_pending_expiry(db, subscription, SimpleNamespace(expire_at=target))
            await db.commit()
        service = RemnaWaveWebhookService(AsyncMock())
        monkeypatch.setattr(service, '_notify_user', AsyncMock())
        await service._handle_user_modified(
            db,
            user,
            subscription,
            {
                'id': 555,
                'status': 'ACTIVE',
                'expireAt': original.isoformat(),
            },
        )
        await db.refresh(subscription)
        assert subscription.end_date == (original if confirmed else target)


@pytest.mark.parametrize('event', ['user.expired', 'panel-truth'])
async def test_pending_intent_does_not_prevent_actual_expiry(postgres_database, monkeypatch, event):
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user, subscription, _ = await _seed(db, datetime.now(UTC))
        subscription.end_date = subscription.pending_panel_expire_at = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()
        service = RemnaWaveWebhookService(AsyncMock())
        monkeypatch.setattr(service, '_notify_user', AsyncMock())
        payload = {
            'id': 555,
            'status': 'EXPIRED',
            'expireAt': (subscription.end_date - timedelta(days=30)).isoformat(),
        }
        if event == 'panel-truth':
            from app.services.panel_sync.projection import (
                PANEL_TRUTH,
                project_onto_subscription,
                read_panel_user,
            )

            project_onto_subscription(subscription, read_panel_user(payload), policy=PANEL_TRUTH)
            await db.commit()
        else:
            await service._process_user_event(db, event, payload, service._handle_user_expired)
        await db.refresh(subscription)
        assert subscription.status == 'expired'


async def test_daily_charge_persists_recoverable_expiry(postgres_database):
    from app.database.crud.subscription import update_daily_charge_time

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        _user, subscription, _ = await _seed(db, datetime.now(UTC))
        subscription.status = 'active'
        subscription.is_trial = False
        subscription.end_date = datetime.now(UTC) - timedelta(days=2)
        await db.commit()
        await update_daily_charge_time(db, subscription)
        await db.refresh(subscription)
        assert subscription.pending_panel_expire_at == subscription.end_date
        assert subscription.end_date > datetime.now(UTC)
