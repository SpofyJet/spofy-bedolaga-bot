"""Feature (#2): admin "reset subscription" — fully zero out a subscription
("as if the user never spammed it") WITHOUT deleting the user from the bot DB,
so support tickets survive. The RemnaWave panel user is DISABLED (not deleted).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import app.services.subscription_service as ss
from app.database.crud.subscription import reset_subscription
from app.database.models import SubscriptionStatus


def _sub(**kw) -> SimpleNamespace:
    base = dict(
        id=7,
        user_id=1,
        status=SubscriptionStatus.ACTIVE.value,
        end_date=datetime.now(UTC) + timedelta(days=1000),  # spammed far into the future
        connected_squads=['sq1', 'sq2'],
        traffic_used_gb=42.5,
        autopay_enabled=True,
        # RemnaWave 3.0.0: панельный юзер адресуется числовым id, а не uuid.
        remnawave_id=7001,
    )
    base.update(kw)
    return SimpleNamespace(**base)


async def test_reset_subscription_zeroes_fields():
    sub = _sub()
    before = datetime.now(UTC)

    await reset_subscription(AsyncMock(), sub, commit=False)

    assert sub.status == SubscriptionStatus.DISABLED.value
    # spammed days gone: end_date snapped to ~now
    assert before <= sub.end_date <= datetime.now(UTC)
    assert sub.connected_squads == []
    assert sub.traffic_used_gb == 0.0
    assert sub.autopay_enabled is False


async def test_reset_with_panel_singletariff_falls_back_to_user_panel_id(monkeypatch):
    disabled: list[int] = []

    async def fake_disable(self, panel_user_id):
        disabled.append(panel_user_id)
        return True

    monkeypatch.setattr(ss.SubscriptionService, 'disable_remnawave_user', fake_disable)

    sub = _sub(remnawave_id=None)
    user = SimpleNamespace(id=1, remnawave_id=9001)

    await ss.reset_subscription_with_panel(AsyncMock(), user, sub)

    assert disabled == [9001]  # legacy single-tariff fallback is correct here


async def test_reset_with_panel_no_panel_id_skips_panel(monkeypatch):
    called: list[int] = []

    async def fake_disable(self, panel_user_id):
        called.append(panel_user_id)
        return True

    monkeypatch.setattr(ss.SubscriptionService, 'disable_remnawave_user', fake_disable)

    sub = _sub(remnawave_id=None)
    user = SimpleNamespace(id=1, remnawave_id=None)

    result = await ss.reset_subscription_with_panel(AsyncMock(), user, sub)

    assert called == []  # nothing to disable
    assert result['panel_disabled'] is False
    assert sub.status == SubscriptionStatus.DISABLED.value  # bot-side reset still applied


async def test_reset_with_panel_survives_panel_error(monkeypatch):
    """A panel disable failure must not block the bot-side reset (best effort)."""

    async def boom(self, panel_user_id):
        raise RuntimeError('panel down')

    monkeypatch.setattr(ss.SubscriptionService, 'disable_remnawave_user', boom)

    sub = _sub(remnawave_id=7001)
    user = SimpleNamespace(id=1, remnawave_id=None)

    result = await ss.reset_subscription_with_panel(AsyncMock(), user, sub)

    assert result['panel_disabled'] is False
    assert sub.status == SubscriptionStatus.DISABLED.value


async def test_user_modified_does_not_resurrect_disabled_end_date():
    """A user.modified webhook carrying a stale FUTURE expireAt must NOT restore the
    end_date of a subscription the bot deliberately DISABLED (e.g. after reset) —
    otherwise the spammed days would silently come back."""
    import app.services.remnawave_webhook_service as rw

    svc = rw.RemnaWaveWebhookService(MagicMock())
    svc._stamp_webhook_update = MagicMock()

    now = datetime.now(UTC)
    reset_end = now
    sub = SimpleNamespace(
        id=7,
        status=SubscriptionStatus.DISABLED.value,
        end_date=reset_end,
        traffic_limit_gb=0,
        traffic_used_gb=0.0,
        connected_squads=[],
        subscription_url='https://x',
        subscription_crypto_link='crypto',
        updated_at=now,
    )
    user = SimpleNamespace(id=1, telegram_id=123)
    data = {'expireAt': (now + timedelta(days=900)).isoformat(), 'status': 'DISABLED'}

    await svc._handle_user_modified(AsyncMock(), user, sub, data)

    assert sub.end_date == reset_end  # NOT pushed back to +900 days
    assert sub.status == SubscriptionStatus.DISABLED.value


async def test_user_modified_still_syncs_end_date_for_active():
    """Regression guard: ACTIVE subs still get end_date synced from the panel."""
    import app.services.remnawave_webhook_service as rw

    svc = rw.RemnaWaveWebhookService(MagicMock())
    svc._stamp_webhook_update = MagicMock()

    now = datetime.now(UTC)
    sub = SimpleNamespace(
        id=7,
        status=SubscriptionStatus.ACTIVE.value,
        end_date=now + timedelta(days=10),
        traffic_limit_gb=0,
        traffic_used_gb=0.0,
        connected_squads=[],
        subscription_url='https://x',
        subscription_crypto_link='crypto',
        updated_at=now,
    )
    user = SimpleNamespace(id=1, telegram_id=123)
    new_expiry = now + timedelta(days=30)
    data = {'expireAt': new_expiry.isoformat(), 'status': 'ACTIVE'}

    await svc._handle_user_modified(AsyncMock(), user, sub, data)

    assert abs((sub.end_date - new_expiry).total_seconds()) < 2  # synced from panel
