from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class PurchasePersisted(BaseException):
    """Stop at the persistence boundary, before external side effects."""


@pytest.mark.postgres
@pytest.mark.parametrize(('carry', 'reset'), [(False, False), (False, True), (True, False), (True, True)])
@pytest.mark.parametrize('trial', [False, True])
async def test_classic_purchase_persists_expiry_balance_and_conversion(
    postgres_database, monkeypatch, carry, reset, trial
):
    from sqlalchemy import func, select

    from app.database.models import (
        Base,
        Subscription,
        SubscriptionConversion,
        Transaction,
        User,
    )
    from app.services import subscription_purchase_service as m
    from tests.fixtures.postgres_db import postgres_session

    monkeypatch.setattr(settings, 'TRIAL_ADD_REMAINING_DAYS_TO_PAID', carry)
    monkeypatch.setattr(settings, 'TARIFF_SWITCH_RESET_FREE_DAYS', reset)
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(m, 'datetime', FrozenDateTime)
    panel = SimpleNamespace(create_remnawave_user=AsyncMock(), update_remnawave_user=AsyncMock())
    monkeypatch.setattr(m, 'SubscriptionService', lambda: panel)
    remaining = timedelta(days=4, hours=19, minutes=12)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        user = User(id=42, telegram_id=42, first_name='Test', language='ru', status='active', balance_kopeks=100000)
        subscription = Subscription(
            id=7,
            user_id=42,
            is_trial=trial,
            status='active',
            start_date=NOW - timedelta(days=2),
            end_date=NOW + remaining,
            traffic_limit_gb=100,
            device_limit=2,
            connected_squads=[],
        )
        db.add_all([user, subscription])
        await db.commit()
        context = SimpleNamespace(user=user, subscription=subscription)
        pricing = SimpleNamespace(
            final_total=1000,
            base_original_total=1000,
            promo_discount_value=0,
            server_ids=[],
            months=1,
            selection=SimpleNamespace(period=SimpleNamespace(days=30), traffic_value=100, devices=2, servers=[]),
        )
        result = await m.MiniAppSubscriptionPurchaseService().submit_purchase(db, context, pricing)
        await db.refresh(subscription)
        await db.refresh(user)
        expected_remaining = remaining if not trial or (carry and not reset) else timedelta()
        assert subscription.end_date == NOW + timedelta(days=30) + expected_remaining
        assert subscription.pending_panel_expire_at == subscription.end_date
        assert subscription.is_trial is False
        assert user.balance_kopeks == 99000
        assert result['was_trial_conversion'] is trial
        assert await db.scalar(select(func.count()).select_from(SubscriptionConversion)) == int(trial)
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 1
        assert transactions[0].amount_kopeks == -1000
