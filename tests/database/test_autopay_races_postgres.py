"""Autopay must recheck consent and due date under the billing transaction lock."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Transaction
from app.services import monitoring_service as monitoring, subscription_auto_purchase_service as auto
from tests.database.test_renewal_survives_stale_panel_snapshot_postgres import (
    BALANCE,
    _seed,
)
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres
TABLES = list(Base.metadata.sorted_tables)


@pytest.fixture(autouse=True)
def quiet_settings(monkeypatch):
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    monkeypatch.setattr(settings, 'RESET_TRAFFIC_ON_PAYMENT', False)
    monkeypatch.setattr(settings, 'RESET_DEVICES_ON_RENEWAL', False)
    monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', AsyncMock())
    monkeypatch.setattr(monitoring.cache, 'exists', AsyncMock(return_value=True))


def worker():
    service = monitoring.MonitoringService(bot=None)
    service.subscription_service = SimpleNamespace(
        update_remnawave_user=AsyncMock(return_value=SimpleNamespace(id=555))
    )
    return service


@pytest.mark.parametrize('mode', ['classic', 'tariffs'])
@pytest.mark.parametrize('entry', ['monitor', 'topup'])
async def test_imported_subscription_with_autopay_off_never_charges(postgres_database, monkeypatch, mode, entry):
    async with postgres_session(postgres_database, TABLES) as db:
        user, sub, _ = await _seed(db, datetime.now(UTC))
        sub.tariff_id = None
        sub.autopay_enabled = False
        sub.end_date = datetime.now(UTC) - timedelta(minutes=30)
        sub.status = 'expired'
        sub.updated_at = datetime.now(UTC) - timedelta(days=1)
        await db.commit()
        original_end = sub.end_date
        if entry == 'monitor':
            await worker()._process_autopayments(db)
        else:
            assert await auto.try_auto_extend_expired_after_topup(db, user) is False
        await db.refresh(user)
        await db.refresh(sub)
        assert user.balance_kopeks == BALANCE
        assert sub.end_date == original_end
        assert list(await db.scalars(select(Transaction))) == []
