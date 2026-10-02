"""Spofy: на лимите трафика отключаются только обходы (сквад Bypass-Off).

Закреплено: кому положен даунгрейд, что уходит в панель для помеченной подписки,
что импорт из панели не принимает Bypass-Off за смену тарифа, как вебхуки и сверка
переводят подписку туда и обратно, и диплинки /start renew | traffic.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.database.models import SubscriptionStatus
from app.external.remnawave_api import UserStatus
from app.services import bypass_downgrade as rules
from app.services.bypass_downgrade_service import BypassDowngradeService
from app.services.panel_sync import PanelSnapshot, build_panel_payload, project_onto_subscription


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
BYPASS = 'dbdb505a-245e-412b-8eee-38cf6db1a383'
OFF = '61515668-7488-4c46-9835-062600802bf0'
REGULAR = 'a7291803-07a3-4ca8-943e-25a1d4e649f6'


@pytest.fixture
def enforcing(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_DOWNGRADE_MODE', 'true')
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', BYPASS)
    monkeypatch.setattr(settings, 'BYPASS_OFF_SQUAD_UUID', OFF)
    monkeypatch.setattr(settings, 'BYPASS_FALLBACK_SQUAD_UUID', REGULAR)


def _user(**kw):
    base = dict(id=10, telegram_id=555, username='tg', full_name='Иван', email=None, status='active', language='ru')
    base.update(kw)
    return SimpleNamespace(**base)


def _sub(**kw):
    base = dict(
        id=101,
        user_id=10,
        status=SubscriptionStatus.ACTIVE.value,
        is_trial=False,
        end_date=NOW + timedelta(days=30),
        traffic_limit_gb=100,
        traffic_used_gb=100.0,
        connected_squads=[BYPASS],
        bypass_suspended_at=None,
        tariff=None,
        tariff_id=None,
        remnawave_id=None,
        remnawave_short_id='ab12cd',
        device_limit=3,
        grace_candidate_reason=None,
        grace_candidate_at=None,
        updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ==================== кому положен даунгрейд ====================


def test_paid_bypass_subscription_with_exhausted_quota_is_eligible(enforcing):
    assert rules.ineligibility_reason(_user(), _sub(), now=NOW) is None


@pytest.mark.parametrize(
    ('sub_kw', 'user_kw', 'tariff', 'reason'),
    [
        ({'is_trial': True}, {}, None, 'trial'),
        ({}, {}, SimpleNamespace(is_daily=True), 'daily'),
        ({'end_date': NOW - timedelta(minutes=1)}, {}, None, 'expired'),
        ({'status': SubscriptionStatus.DISABLED.value}, {}, None, 'status'),
        ({'connected_squads': [REGULAR]}, {}, None, 'no_bypass_squad'),
        ({'traffic_limit_gb': 0}, {}, None, 'unlimited'),
        ({}, {'status': 'blocked'}, None, 'user_inactive'),
    ],
)
def test_ineligible(enforcing, sub_kw, user_kw, tariff, reason):
    assert rules.ineligibility_reason(_user(**user_kw), _sub(**sub_kw), tariff=tariff, now=NOW) == reason


def test_limited_status_is_still_eligible(enforcing):
    # Панель выставляет LIMITED раньше, чем приходит вебхук или сверка.
    assert rules.ineligibility_reason(_user(), _sub(status=SubscriptionStatus.LIMITED.value), now=NOW) is None


def test_without_squads_configured_nothing_is_eligible(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', '')
    monkeypatch.setattr(settings, 'BYPASS_OFF_SQUAD_UUID', '')
    assert rules.ineligibility_reason(_user(), _sub(), now=NOW) == 'not_configured'


# ==================== что уходит в панель ====================


def test_suspended_subscription_goes_to_bypass_off_unlimited_and_active(enforcing):
    payload = build_panel_payload(_user(), _sub(bypass_suspended_at=NOW), multi_tariff=False, now=NOW)

    assert payload.active_internal_squads == (OFF,)
    assert payload.traffic_limit_bytes == 0
    assert payload.status == UserStatus.ACTIVE
    assert payload.end_date == NOW + timedelta(days=30)


def test_not_suspended_subscription_keeps_tariff_squads_and_limit(enforcing):
    payload = build_panel_payload(_user(), _sub(), multi_tariff=False, now=NOW)

    assert payload.active_internal_squads == (BYPASS,)
    assert payload.traffic_limit_bytes == 100 * 1024**3


@pytest.mark.parametrize(
    'change',
    [
        {'traffic_limit_gb': 150},  # докупили трафик
        {'traffic_used_gb': 0.0},  # продление / сброс трафика обнулили расход
    ],
)
def test_bypass_returns_once_quota_is_no_longer_exhausted(enforcing, change):
    payload = build_panel_payload(_user(), _sub(bypass_suspended_at=NOW, **change), multi_tariff=False, now=NOW)

    assert payload.active_internal_squads == (BYPASS,)
    assert payload.traffic_limit_bytes > 0


def test_mode_false_ignores_leftover_marks(enforcing, monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_DOWNGRADE_MODE', 'false')
    payload = build_panel_payload(_user(), _sub(bypass_suspended_at=NOW), multi_tariff=False, now=NOW)

    assert payload.active_internal_squads == (BYPASS,)


def test_tariff_squad_sync_keeps_suspended_account_in_bypass_off(enforcing):
    from app.services.panel_sync.writer import patch_panel_squads

    update = AsyncMock()
    import asyncio

    asyncio.run(
        patch_panel_squads(
            None,
            user_id=7,
            squads=[BYPASS, 'new-squad'],
            external_squad_uuid=None,
            update_call=update,
            subscription=_sub(bypass_suspended_at=NOW),
        )
    )

    assert update.await_args.kwargs['active_internal_squads'] == [OFF]


# ==================== импорт из панели ====================


def test_import_does_not_take_bypass_off_as_a_tariff_change(enforcing):
    subscription = _sub(
        bypass_suspended_at=NOW,
        traffic_used_gb=100.0,
        remnawave_short_uuid='abc',
        subscription_url='https://x',
        subscription_crypto_link=None,
        grace_tail_expire_at=None,
        grace_session_open=False,
        grace_overlay_expire_at=None,
        last_webhook_update_at=None,
    )
    snapshot = PanelSnapshot(
        status='ACTIVE',
        expire_at=subscription.end_date,
        squads=(OFF,),
        traffic_limit_gb=0,
        traffic_used_gb=101.0,
    )

    changed = project_onto_subscription(subscription, snapshot, now=NOW)

    assert subscription.connected_squads == [BYPASS]
    assert subscription.traffic_limit_gb == 100
    assert 'connected_squads' not in changed and 'traffic_limit_gb' not in changed


def test_suspended_snapshot_recognition(enforcing):
    assert rules.is_suspended_snapshot([OFF])
    assert rules.is_suspended_snapshot([OFF, REGULAR])
    assert not rules.is_suspended_snapshot([BYPASS])
    assert not rules.is_suspended_snapshot([OFF, BYPASS])


# ==================== вебхуки ====================


def _service(push_ok=True):
    service = BypassDowngradeService()
    service._push = AsyncMock(return_value=push_ok)
    service.notify = AsyncMock()
    service._load_tariff = AsyncMock(return_value=None)
    return service


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def test_limited_webhook_suspends_instead_of_limiting(enforcing):
    import asyncio

    service = _service()
    subscription = _sub(status=SubscriptionStatus.ACTIVE.value, traffic_used_gb=97.0)

    handled = asyncio.run(
        service.handle_limited_webhook(_db(), _user(), subscription, {'usedTrafficBytes': 100 * 1024**3})
    )

    assert handled is True
    assert subscription.bypass_suspended_at is not None
    assert subscription.status == SubscriptionStatus.ACTIVE.value
    assert subscription.traffic_used_gb == pytest.approx(100.0)
    service._push.assert_awaited_once()
    assert service.notify.await_args.args[1] == 'BYPASS_SUSPENDED'


def test_limited_webhook_for_ineligible_subscription_falls_through(enforcing):
    import asyncio

    service = _service()
    handled = asyncio.run(service.handle_limited_webhook(_db(), _user(), _sub(is_trial=True), {}))

    assert handled is False
    service._push.assert_not_awaited()


def test_observe_mode_only_logs(enforcing, monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, 'BYPASS_DOWNGRADE_MODE', 'observe')
    service = _service()
    subscription = _sub()

    handled = asyncio.run(service.handle_limited_webhook(_db(), _user(), subscription, {}))

    assert handled is False
    assert subscription.bypass_suspended_at is None
    service._push.assert_not_awaited()


def test_traffic_reset_webhook_restores_and_says_bypass_is_back(enforcing):
    import asyncio

    service = _service()
    subscription = _sub(bypass_suspended_at=NOW, traffic_used_gb=0.0)
    subscription.actual_status = 'active'

    replaced = asyncio.run(service.handle_traffic_reset_webhook(_db(), _user(), subscription))

    assert replaced is True
    assert subscription.bypass_suspended_at is None
    service._push.assert_awaited_once()
    assert service.notify.await_args.args[1] == 'BYPASS_RESTORED'


def test_traffic_reset_without_mark_keeps_the_usual_message(enforcing):
    import asyncio

    service = _service()
    assert asyncio.run(service.handle_traffic_reset_webhook(_db(), _user(), _sub())) is False


# ==================== сверка ====================


def _reconcile(service, flagged, candidates):
    import asyncio

    service._load = AsyncMock(side_effect=[flagged, candidates])
    service._check_squad_drift = AsyncMock()
    return asyncio.run(service.reconcile(_db()))


def _live(**kw):
    sub = _sub(**kw)
    sub.user = _user()
    sub.actual_status = 'limited' if sub.status == SubscriptionStatus.LIMITED.value else 'active'
    return sub


def test_reconcile_suspends_missed_webhook_and_restores_after_purchase(enforcing):
    service = _service()
    missed = _live(status=SubscriptionStatus.LIMITED.value)
    bought = _live(bypass_suspended_at=NOW, traffic_limit_gb=150)

    stats = _reconcile(service, flagged=[bought], candidates=[missed])

    assert stats['suspended'] == 1 and stats['restored'] == 1
    assert missed.bypass_suspended_at is not None and missed.status == SubscriptionStatus.ACTIVE.value
    assert bought.bypass_suspended_at is None


def test_reconcile_is_idempotent(enforcing):
    service = _service()
    steady = _live(bypass_suspended_at=NOW)

    stats = _reconcile(service, flagged=[steady], candidates=[])

    assert not any(stats.values())
    service._push.assert_not_awaited()
    service.notify.assert_not_awaited()


def test_reconcile_repushes_when_panel_limited_the_account_anyway(enforcing):
    service = _service()
    stuck = _live(bypass_suspended_at=NOW, status=SubscriptionStatus.LIMITED.value)

    stats = _reconcile(service, flagged=[stuck], candidates=[])

    assert stats['resuspended'] == 1
    assert stuck.status == SubscriptionStatus.ACTIVE.value
    service.notify.assert_not_awaited()  # человек уже знает


def test_rollback_mode_false_clears_marks_silently(enforcing, monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_DOWNGRADE_MODE', 'false')
    service = _service()
    marked = _live(bypass_suspended_at=NOW)

    service._load = AsyncMock(side_effect=[[marked]])
    import asyncio

    stats = asyncio.run(service.reconcile(_db()))

    assert stats['cleared'] == 1
    assert marked.bypass_suspended_at is None
    service.notify.assert_not_awaited()


# ==================== диплинки ====================


@pytest.mark.parametrize(('action', 'callback'), [('traffic', 'buy_traffic'), ('renew', 'subscription_extend')])
def test_deeplinks_answer_with_one_button(monkeypatch, action, callback):
    import asyncio

    from app.handlers import subscription_deeplinks

    monkeypatch.setattr(subscription_deeplinks, 'get_subscription_by_user_id', AsyncMock(return_value=_sub()))
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default')
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    message = MagicMock()
    message.answer = AsyncMock()

    handled = asyncio.run(subscription_deeplinks.open_subscription_deeplink(message, _user(), _db(), action))

    assert handled is True
    markup = message.answer.await_args.kwargs['reply_markup']
    assert [row[0].callback_data for row in markup.inline_keyboard] == [callback]


def test_deeplink_without_subscription_falls_through(monkeypatch):
    import asyncio

    from app.handlers import subscription_deeplinks

    monkeypatch.setattr(subscription_deeplinks, 'get_subscription_by_user_id', AsyncMock(return_value=None))
    message = MagicMock()
    message.answer = AsyncMock()

    assert asyncio.run(subscription_deeplinks.open_subscription_deeplink(message, _user(), _db(), 'renew')) is False
    message.answer.assert_not_awaited()
