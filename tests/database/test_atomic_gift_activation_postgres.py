"""Две одновременные активации одного подарка — на PostgreSQL.

activate_purchase блокирует строку покупки (FOR UPDATE) и продлевает подписку без
коммита, но сервис панели при успехе сам делает commit — продление уходило в базу,
а покупка оставалась PENDING_ACTIVATION до второго коммита. Второй запрос (двойное
нажатие «Активировать подарок», повтор зависших активаций) в этот момент получал
блокировку, видел PENDING_ACTIVATION и продлевал ещё раз: два срока за один подарок.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, GuestPurchase, GuestPurchaseStatus, Subscription, Tariff, User
from app.services import guest_purchase_service as guest
from tests.fixtures.postgres_db import postgres_sessions


pytestmark = pytest.mark.postgres

TOKEN = 'g' * 64


class _Panel:
    """Панель ответила: как настоящий create_remnawave_user — ссылка в подписку и commit."""

    calls = 0

    async def create_remnawave_user(self, db, subscription, **kwargs):
        type(self).calls += 1
        subscription.subscription_url = 'https://example.com/sub'
        await db.commit()
        return SimpleNamespace(id=123)


async def test_two_concurrent_activations_of_one_gift_extend_once(postgres_database, monkeypatch):
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    _Panel.calls = 0
    monkeypatch.setattr(guest, 'SubscriptionService', _Panel)
    for name in ['send_guest_notification', '_send_admin_notification']:
        monkeypatch.setattr(guest, name, AsyncMock())
    now = datetime.now(UTC)
    end = now + timedelta(days=10)

    async with postgres_sessions(postgres_database, list(Base.metadata.sorted_tables), count=3) as (db, first, second):
        db.add_all(
            [
                User(id=42, telegram_id=42, first_name='Test', language='ru', auth_type='telegram', status='active'),
                Tariff(
                    id=1,
                    name='Target',
                    is_active=True,
                    traffic_limit_gb=100,
                    device_limit=2,
                    period_prices={'30': 300},
                    allowed_squads=['test-squad'],
                ),
            ]
        )
        await db.commit()
        db.add_all(
            [
                Subscription(
                    id=7,
                    user_id=42,
                    tariff_id=1,
                    is_trial=False,
                    status='active',
                    start_date=now - timedelta(days=20),
                    end_date=end,
                    traffic_limit_gb=100,
                    traffic_used_gb=0.0,
                    device_limit=2,
                    connected_squads=['test-squad'],
                    remnawave_id=123,
                ),
                GuestPurchase(
                    token=TOKEN,
                    user_id=42,
                    tariff_id=1,
                    period_days=30,
                    amount_kopeks=300,
                    contact_type='telegram',
                    contact_value='42',
                    is_gift=True,
                    status=GuestPurchaseStatus.PENDING_ACTIVATION.value,
                ),
            ]
        )
        await db.commit()

        async def request(session):
            # Как запрос бота или кабинета: по окончании сессия закрывается и отпускает блокировки.
            try:
                return await guest.activate_purchase(session, TOKEN)
            finally:
                await session.rollback()

        results = await asyncio.wait_for(
            asyncio.gather(request(first), request(second), return_exceptions=True),
            15,
        )

        errors = [repr(r) for r in results if isinstance(r, BaseException)]
        db.expire_all()
        sub = await db.get(Subscription, 7)
        purchase = (await db.execute(select(GuestPurchase).where(GuestPurchase.token == TOKEN))).scalar_one()
        status, end_date = purchase.status, sub.end_date

    assert errors == []
    assert status == GuestPurchaseStatus.DELIVERED.value
    assert abs((end_date - (end + timedelta(days=30))).total_seconds()) < 5, 'подарок продлил подписку один раз'
    assert _Panel.calls == 1
