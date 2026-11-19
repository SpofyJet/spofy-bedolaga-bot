from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cabinet.routes.subscription_modules.purchase import _build_tariff_response, purchase_tariff
from app.cabinet.schemas.subscription import TariffPurchaseRequest
from app.config import settings
from app.database.models import Base, Subscription, SubscriptionStatus, Tariff, User
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


class _Panel:
    async def update_remnawave_user(self, db, subscription, **kwargs):
        return SimpleNamespace(id=9001, used_traffic_bytes=0)

    async def create_remnawave_user(self, db, subscription, **kwargs):
        return SimpleNamespace(id=9001, used_traffic_bytes=0)

    async def enable_remnawave_user(self, panel_user_id, db=None):
        return True


@pytest.fixture(autouse=True)
def panel(monkeypatch):
    import app.services.subscription_renewal_service as renewal_module
    import app.services.subscription_service as subscription_service_module

    monkeypatch.setattr(subscription_service_module, 'SubscriptionService', _Panel)
    monkeypatch.setattr(renewal_module, 'SubscriptionService', _Panel)
    monkeypatch.setattr(renewal_module, 'with_admin_notification_service', AsyncMock())
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)


async def _seed(db, *, subscription=False):
    db.add_all(
        [
            User(id=1, telegram_id=1001, first_name='U', language='ru', status='active', balance_kopeks=100000),
            Tariff(
                id=1,
                name='Стандартный',
                description='',
                is_active=True,
                is_daily=False,
                period_prices={'14': 15900, '30': 17900},
                traffic_limit_gb=0,
                device_limit=3,
                device_price_kopeks=5900,
                allowed_squads=['squad-1'],
                display_order=1,
            ),
        ]
    )
    if subscription:
        now = datetime.now(UTC)
        db.add(
            Subscription(
                id=10,
                remnawave_short_id='s1',
                remnawave_id=9001,
                user_id=1,
                status=SubscriptionStatus.ACTIVE.value,
                is_trial=False,
                start_date=now - timedelta(days=5),
                end_date=now + timedelta(days=10),
                traffic_limit_gb=0,
                traffic_used_gb=0.0,
                device_limit=3,
                tariff_id=1,
                connected_squads=['squad-1'],
            )
        )
    await db.commit()
    return await db.get(User, 1), await db.get(Tariff, 1)


async def test_month_periods_offer_device_counts_priced_like_the_purchase(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        user, tariff = await _seed(db)
        response = await _build_tariff_response(db, tariff, user=user, subscription=None)
        periods = {period['days']: period for period in response['periods']}

        assert 'device_options' not in periods[14]
        options = periods[30]['device_options']
        assert [option['devices'] for option in options] == [3, 5, 7, 10]
        assert options[0]['included'] is True and options[0]['price_kopeks'] == periods[30]['price_kopeks']
        assert options[1]['price_kopeks'] == 17900 + 2 * 5900


async def test_cabinet_purchase_provisions_and_charges_the_chosen_devices(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        user, _ = await _seed(db)
        response = await purchase_tariff(TariffPurchaseRequest(tariff_id=1, period_days=30, device_limit=5), user, db)

        assert response['success'] is True
        subscription = (await db.execute(Subscription.__table__.select())).first()
        await db.refresh(user)
        assert subscription.device_limit == 5
        assert user.balance_kopeks == 100000 - 17900 - 2 * 5900


async def test_renewing_the_same_tariff_ignores_a_device_choice(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        user, _ = await _seed(db, subscription=True)
        response = await purchase_tariff(TariffPurchaseRequest(tariff_id=1, period_days=30, device_limit=7), user, db)

        assert response['success'] is True
        subscription = await db.get(Subscription, 10)
        await db.refresh(user)
        assert subscription.device_limit == 3
        assert user.balance_kopeks == 100000 - 17900
