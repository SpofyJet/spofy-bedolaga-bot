from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Tariff, User
from app.handlers.subscription import tariff_purchase as telegram
from app.services import subscription_auto_purchase_service as auto
from app.services.user_cart_service import user_cart_service
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres


class PanelBoundary(BaseException):
    pass


def _buttons(callback):
    return [b for row in callback.message.edit_text.await_args.kwargs['reply_markup'].inline_keyboard for b in row]


@pytest.mark.parametrize('flow', ['telegram', 'auto'])
async def test_chosen_devices_are_priced_and_provisioned(postgres_database, monkeypatch, flow):
    from app.services import subscription_renewal_service as renewal

    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)
    monkeypatch.setattr(renewal, 'with_admin_notification_service', AsyncMock())
    monkeypatch.setattr(user_cart_service, 'save_user_cart', AsyncMock())
    panel_call = AsyncMock(side_effect=PanelBoundary)
    panel = SimpleNamespace(
        create_remnawave_user=panel_call, update_remnawave_user=panel_call, sync_remnawave_user=panel_call
    )
    monkeypatch.setattr(auto, 'SubscriptionService', lambda: panel)

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user = User(id=42, telegram_id=42, first_name='Test', language='ru', status='active', balance_kopeks=10000)
        tariff = Tariff(
            id=1,
            name='Test',
            is_active=True,
            is_daily=False,
            traffic_limit_gb=100,
            device_limit=2,
            device_price_kopeks=100,
            period_prices={'30': 300},
            allowed_squads=['test-squad'],
        )
        db.add_all([user, tariff])
        await db.commit()

        if flow == 'telegram':
            callback = SimpleNamespace(
                data='tariff_period:1:30', answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock())
            )
            callback.model_copy = lambda update: SimpleNamespace(**{**callback.__dict__, **update})
            state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=42, user_id=42))
            await telegram.select_tariff_period(callback, user, db, state)
            step = _buttons(callback)
            assert [b.callback_data for b in step][-2:] == ['tariff_dev:1:30:2', 'tariff_select:1']
            callback.data = 'tariff_dev:1:30:4'
            await telegram.select_tariff_devices(callback, user, db, state)
            callback.data = next(
                b.callback_data for b in _buttons(callback) if b.callback_data.startswith('tariff_confirm:')
            )
            operation = telegram.confirm_tariff_purchase(callback, user, db, state)
        else:
            operation = auto._auto_purchase_tariff(
                db, user, {'tariff_id': 1, 'period_days': 30, 'total_price': 500, 'device_limit': 4}
            )

        with pytest.raises(PanelBoundary):
            await operation

        await db.refresh(user)
        subscription = (await db.execute(select(Subscription).where(Subscription.user_id == 42))).scalar_one()
        assert subscription.device_limit == 4
        assert user.balance_kopeks == 10000 - 500
