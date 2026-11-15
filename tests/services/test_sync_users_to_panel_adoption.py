"""`sync_users_to_panel`: массовая синхронизация бот → панель.

Это единственный путь, который админ может запустить сразу на ВСЮ базу
(«Синхронизировать в панель»). После миграции 0104 и до прогона бэкфила у
каждой строки `remnawave_id IS NULL`, поэтому без подхвата по `shortUuid`
один клик заводил бы дубль панельного аккаунта на каждую подписку и затирал
`remnawave_short_uuid` — единственный ключ, которым оригинал ещё можно найти.

Мутационная проверка показала, что раньше удаление всей этой ветки проходило
при зелёном прогоне, поэтому сценарии пиннятся здесь.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.database.crud.subscription as crud_sub_mod
import app.services.panel_sync.lease as lease_mod
from app.database.models import SubscriptionStatus
from app.services.remnawave_service import RemnaWaveService


def _user():
    return SimpleNamespace(
        id=1,
        telegram_id=555,
        username='u',
        full_name='User',
        email=None,
        remnawave_id=None,
    )


def _subscription(*, panel_id=None, short_uuid='aBcD12'):
    return SimpleNamespace(
        id=500,
        user=_user(),
        user_id=1,
        status=SubscriptionStatus.ACTIVE.value,
        end_date=datetime.now(UTC) + timedelta(days=30),
        traffic_limit_gb=50,
        connected_squads=[],
        tariff=None,
        remnawave_id=panel_id,
        remnawave_short_uuid=short_uuid,
        remnawave_short_id='sid500',
        subscription_url='',
        subscription_crypto_link='',
        device_limit=1,
    )


def _db() -> AsyncMock:
    """Сессия-двойник: единственный запрос сервиса к базе — «не держит ли этот
    панельный id другая строка подписок»."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None, first=lambda: None))
    return db


@pytest.fixture
def harness(monkeypatch):
    """Один батч из одной подписки, gracce-lease разрешён, клиент — мок."""
    subscription = _subscription()
    api = AsyncMock()
    api.get_user_devices_all.return_value = {'total': 0, 'devices': []}

    batches = [[subscription], []]

    async def fake_batch(db, offset=0, limit=500):
        return batches.pop(0) if batches else []

    @asynccontextmanager
    async def fake_lease(subscription_id):
        yield SimpleNamespace(allowed=True, subscription=subscription)

    monkeypatch.setattr(crud_sub_mod, 'get_subscriptions_batch', fake_batch)
    monkeypatch.setattr(lease_mod, 'subscription_update_lease', fake_lease)

    service = RemnaWaveService()
    service._config_error = None

    @asynccontextmanager
    async def fake_client():
        yield api

    monkeypatch.setattr(service, 'get_api_client', fake_client)
    return SimpleNamespace(service=service, api=api, subscription=subscription)


@pytest.mark.asyncio
async def test_single_tariff_writes_identity_onto_the_user(monkeypatch, harness):
    """Мутация «поменять ветки местами» схлопывала все подписки юзера на один id.

    В single-tariff сначала работают фолбэки по telegram_id/email — гасим их,
    чтобы дойти именно до подхвата по shortUuid.
    """
    harness.api.find_users_by_telegram_id.return_value = []
    harness.api.find_users_by_email.return_value = []
    adopted = SimpleNamespace(id=8812, short_uuid='aBcD12', subscription_url='https://s/aBcD12')
    harness.api.get_user_by_short_uuid.return_value = adopted
    harness.api.update_user.return_value = SimpleNamespace(
        id=8812, short_uuid='aBcD12', subscription_url='https://s/aBcD12', happ_crypto_link=None
    )

    await harness.service.sync_users_to_panel(_db())

    assert harness.subscription.user.remnawave_id == 8812
    # Строке id тоже проставляется — но только если его не держит соседняя
    # подписка (колонка частично уникальна, проверка живёт в
    # link_subscription_panel_identity). Именно этот id читают админские экраны
    # по выбранной подписке; раньше массовый проход оставлял их без адреса.
    assert harness.subscription.remnawave_id == 8812
