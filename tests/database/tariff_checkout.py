"""Общая заготовка Postgres-тестов продления тарифа: пользователь, тариф, подписка, фейковая панель."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import CLASSIC_PERIOD_PRICES, settings
from app.database.crud.user import get_user_by_id
from app.database.models import (
    Base,
    Subscription,
    Tariff,
    User,
)
from app.services.subscription_service import SubscriptionService
from tests.database.test_renewal_hwid_postgres import Panel
from tests.fixtures.postgres_db import postgres_session


class QuickRenewalPanel(Panel):
    async def get_user_devices_all(self, user_id):
        return {
            'total': len(self.devices[user_id]),
            'devices': [{'userId': user_id, 'hwid': hwid} for hwid in self.devices[user_id]],
        }


@asynccontextmanager
async def checkout(postgres_database, monkeypatch):
    for name, value in {
        'SALES_MODE': 'tariffs',
        'MULTI_TARIFF_ENABLED': False,
        'DEFAULT_DEVICE_LIMIT': 1,
        'PRICE_30_DAYS': 45000,
        'PRICE_PER_DEVICE': 10000,
        'RESET_TRAFFIC_ON_PAYMENT': False,
        'RESET_DEVICES_ON_RENEWAL': False,
        'ADMIN_NOTIFICATIONS_ENABLED': False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', AsyncMock())
    monkeypatch.setitem(CLASSIC_PERIOD_PRICES, 30, 45000)
    cart_store = AsyncMock()
    monkeypatch.setattr('app.services.user_cart_service.user_cart_service.save_user_cart', cart_store)
    now = datetime.now(UTC)
    end = now + timedelta(days=5)
    panel = QuickRenewalPanel(end)

    @asynccontextmanager
    async def client(self):
        yield panel

    monkeypatch.setattr(SubscriptionService, 'get_api_client', client)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        db.add_all(
            [
                User(id=1, telegram_id=101, language='ru', status='active', balance_kopeks=400000, remnawave_id=9001),
                Tariff(
                    id=1,
                    name='Test',
                    is_active=True,
                    traffic_limit_gb=100,
                    device_limit=1,
                    device_price_kopeks=5000,
                    period_prices={'14': 10000, '30': 20000, '365': 200000},
                    allowed_squads=['test-squad'],
                ),
            ]
        )
        await db.commit()
        sub = Subscription(
            id=10,
            user_id=1,
            tariff_id=1,
            remnawave_id=9001,
            remnawave_short_id='test-10',
            status='active',
            is_trial=False,
            start_date=now - timedelta(days=30),
            end_date=end,
            traffic_limit_gb=100,
            traffic_used_gb=17,
            device_limit=3,
            connected_squads=['test-squad'],
        )
        db.add(sub)
        await db.commit()
        user = await get_user_by_id(db, 1)
        callback = SimpleNamespace(
            data='tariff_renewal',
            answer=AsyncMock(),
            bot=SimpleNamespace(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        state = SimpleNamespace(
            update_data=AsyncMock(), set_state=AsyncMock(), clear=AsyncMock(), get_data=AsyncMock(return_value={})
        )
        yield SimpleNamespace(
            db=db,
            user=user,
            sub=sub,
            callback=callback,
            state=state,
            panel=panel,
            now=now,
            end=end,
            cart_store=cart_store,
        )
