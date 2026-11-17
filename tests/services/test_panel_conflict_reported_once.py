import ast
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock

from app.database.models import SubscriptionStatus
from app.services import (
    paid_traffic_reset_service as resets,
    remnawave_retry_queue as worker,
    subscription_service as service_module,
)
from app.services.panel_sync import PanelAccountOwnedByAnotherUser
from app.services.panel_sync.identity import PanelOwner
from app.services.subscription_service import SubscriptionService


PURCHASE_ROUTE = Path('app/cabinet/routes/subscription_modules/purchase.py')


class Row(NamedTuple):
    id: int
    user_id: int


def _conflict(subscription_id=20):
    return PanelAccountOwnedByAnotherUser(
        subscription_id=subscription_id, panel_user_id=737, owner=PanelOwner(user_id=1, subscription_id=10)
    )


def _subscription():
    return SimpleNamespace(
        id=20,
        user_id=2,
        status=SubscriptionStatus.ACTIVE.value,
        end_date=datetime.now(UTC) + timedelta(days=10),
        traffic_limit_gb=100,
        subscription_url=None,
        subscription_crypto_link=None,
        connected_squads=[],
        tariff=None,
        remnawave_id=None,
        is_trial=False,
        last_webhook_update_at=None,
    )


def _service(monkeypatch):
    service = SubscriptionService()
    user = SimpleNamespace(id=2, telegram_id=200, username='u', full_name='User', email=None, remnawave_id=737)
    monkeypatch.setattr(service_module, 'get_user_by_id', AsyncMock(return_value=user))
    monkeypatch.setattr(service_module, 'resolve_hwid_device_limit_for_payload', lambda s: None)
    monkeypatch.setattr(service_module, 'push_subscription', AsyncMock(side_effect=_conflict()))
    monkeypatch.setattr(service_module, '_reported_panel_conflicts', set())
    monkeypatch.setattr(service_module, 'logger', MagicMock())

    @asynccontextmanager
    async def client():
        yield AsyncMock()

    monkeypatch.setattr(service, 'get_api_client', client)
    return service


async def test_conflict_is_reported_as_an_error_only_once(monkeypatch):
    service = _service(monkeypatch)
    db = AsyncMock()

    assert await service.update_remnawave_user(db, _subscription()) is None
    assert isinstance(service.panel_conflict, PanelAccountOwnedByAnotherUser)
    db.rollback.assert_awaited()
    assert service_module.logger.error.call_count == 1
    assert service_module.logger.error.call_args.kwargs['subscription_id'] == 20
    assert service_module.logger.error.call_args.kwargs['owner_user_id'] == 1

    assert await service.update_remnawave_user(db, _subscription()) is None
    assert service_module.logger.error.call_count == 1


def _queue(monkeypatch, service):
    queue = worker.RemnaWaveRetryQueue()
    queue._recover_pending_expiries = AsyncMock()
    monkeypatch.setattr(resets, 'process_pending_daily_resets', AsyncMock())
    monkeypatch.setattr(
        'app.database.crud.subscription.get_subscription_by_id', AsyncMock(return_value=_subscription())
    )
    monkeypatch.setattr(service_module, 'SubscriptionService', lambda: service)

    @asynccontextmanager
    async def session():
        yield AsyncMock()

    monkeypatch.setattr(worker, 'AsyncSessionLocal', session)
    return queue


async def test_queue_parks_a_conflicted_subscription_instead_of_retrying(monkeypatch):
    service = SimpleNamespace(
        is_configured=True, panel_conflict=_conflict(), create_remnawave_user=AsyncMock(return_value=None)
    )
    queue = _queue(monkeypatch, service)
    queue.enqueue(20, 2)

    await queue.process_pending()

    assert queue.pending_count == 0
    assert queue._parked[20] > time.monotonic()


async def test_queue_still_retries_an_ordinary_failure(monkeypatch):
    service = SimpleNamespace(
        is_configured=True, panel_conflict=None, create_remnawave_user=AsyncMock(return_value=None)
    )
    queue = _queue(monkeypatch, service)
    queue.enqueue(20, 2)

    await queue.process_pending()

    assert queue.pending_count == 1
    assert not queue._parked


async def test_recovery_scan_skips_a_parked_subscription_until_the_pause_ends(monkeypatch):
    queue = worker.RemnaWaveRetryQueue()
    db = AsyncMock()
    db.execute.return_value.all = MagicMock(return_value=[Row(20, 2)])

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(worker, 'AsyncSessionLocal', session)

    queue._parked[20] = time.monotonic() + 60
    await queue._recover_pending_expiries()
    assert queue.pending_count == 0

    queue._parked[20] = time.monotonic() - 1
    await queue._recover_pending_expiries()
    assert queue.pending_count == 1
    assert 20 not in queue._parked


def test_a_new_purchase_on_a_parked_subscription_is_retried_at_once():
    queue = worker.RemnaWaveRetryQueue()
    queue._parked[20] = time.monotonic() + 60

    queue.enqueue(20, 2, action='update')

    assert queue.pending_count == 1
    assert 20 not in queue._parked


def _line(route, predicate, after=0):
    return min(
        node.lineno
        for node in ast.walk(route)
        if isinstance(node, ast.Call) and node.lineno > after and predicate(node)
    )


def _is_call(name):
    return lambda node: isinstance(node.func, ast.Attribute) and node.func.attr == name


def _is_refresh_of(name):
    return lambda node: (
        _is_call('refresh')(node)
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == name
    )


def test_cabinet_purchase_reloads_objects_after_the_panel_sync_before_using_them():
    tree = ast.parse(PURCHASE_ROUTE.read_text(encoding='utf-8'))
    route = next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == 'purchase_tariff'
    )
    sync = _line(route, _is_call('update_remnawave_user'))
    cart = _line(route, _is_call('save_user_cart'), sync)
    notify = _line(route, _is_call('send_subscription_purchase_notification'), sync)

    for name in ('user', 'subscription'):
        assert _line(route, _is_refresh_of(name), sync) < cart
    assert _line(route, _is_refresh_of('transaction'), sync) < notify
