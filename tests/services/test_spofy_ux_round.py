"""Spofy, раунд UX: уведомления, пробный с обходами, устройства.

- «Инфо» без вшитых ссылок на соглашение/политику (кнопки остаются);
- «подписка истекла» не дублируется, если мониторинг погасил её раньше вебхука;
- «новое устройство» молчит первые сутки подписки (человек сам подключает свои);
- порог трафика говорит, сколько ГБ осталось, и что на тарифе с обходами отключатся
  только обходы;
- догоняющие письма после окончания не уходят в тихие часы;
- пробный с квотой на обходы: попадает в Bypass-Off, текст про тариф, а не докупку;
- экран устройств: «🗑» вместо «🔄», при заполненных местах — «Добавить место».
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.database.models import SubscriptionStatus
from app.services import bypass_downgrade as rules
from app.services.remnawave_webhook_service import RemnaWaveWebhookService


BYPASS = 'dbdb505a-245e-412b-8eee-38cf6db1a383'
OFF = '61515668-7488-4c46-9835-062600802bf0'


def _locale(lang: str) -> dict:
    with open(f'app/localization/locales/{lang}.json', encoding='utf-8') as fh:
        return json.load(fh)


# ==================== «Инфо» ====================


@pytest.mark.parametrize('lang', ['ru', 'en'])
def test_info_prompt_has_no_hardcoded_legal_links(lang):
    prompt = _locale(lang)['MENU_INFO_PROMPT']
    assert 'telegra.ph' not in prompt
    assert '<a ' not in prompt


# ==================== вебхуки ====================


def _service() -> RemnaWaveWebhookService:
    svc = RemnaWaveWebhookService(MagicMock())
    svc._notify_user = AsyncMock()
    svc._get_traffic_keyboard = MagicMock(return_value=None)
    svc._get_subscription_keyboard = MagicMock(return_value=None)
    svc._get_renew_keyboard = MagicMock(return_value=None)
    return svc


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, language='ru', telegram_id=None)


async def test_expired_webhook_after_monitoring_does_not_notify_twice(monkeypatch):
    monkeypatch.setattr('app.services.remnawave_webhook_service.grace_access_runtime.consider_candidate', AsyncMock())
    svc = _service()
    db = MagicMock()
    db.commit = AsyncMock()
    subscription = MagicMock()
    subscription.status = SubscriptionStatus.EXPIRED.value

    await svc._handle_user_expired(db, _user(), subscription, {})

    svc._notify_user.assert_not_awaited()


async def test_expired_webhook_first_still_notifies(monkeypatch):
    monkeypatch.setattr('app.services.remnawave_webhook_service.grace_access_runtime.consider_candidate', AsyncMock())
    monkeypatch.setattr('app.services.remnawave_webhook_service.expire_subscription', AsyncMock())
    svc = _service()
    db = MagicMock()
    db.commit = AsyncMock()
    subscription = MagicMock()
    subscription.status = SubscriptionStatus.ACTIVE.value

    await svc._handle_user_expired(db, _user(), subscription, {})

    assert svc._notify_user.await_args.args[1] == 'WEBHOOK_SUB_EXPIRED'


@pytest.mark.parametrize('age_hours', [0.1, 2, 23, 25])
async def test_device_added_always_notifies_the_owner(age_hours):
    """Уведомление о новом устройстве приходит всегда, в том числе в первые сутки: это полезная
    информация (владелец вернул его после того, как оно было убрано как «шум»)."""
    svc = _service()
    subscription = SimpleNamespace(start_date=datetime.now(UTC) - timedelta(hours=age_hours))

    await svc._handle_device_added(None, _user(), subscription, {'hwidUserDevice': {'deviceModel': 'iPhone'}})

    assert svc._notify_user.await_count == 1


async def test_bandwidth_threshold_says_gb_left_and_bypass_note(monkeypatch):
    monkeypatch.setattr('app.utils.notification_prefs.is_traffic_warning_enabled', lambda user: True)
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', BYPASS)
    svc = _service()
    subscription = SimpleNamespace(traffic_limit_gb=100, traffic_used_gb=80.0, connected_squads=[BYPASS])

    await svc._handle_bandwidth_threshold(None, _user(), subscription, {'lastTriggeredThreshold': 80})

    kwargs = svc._notify_user.await_args.kwargs['format_kwargs']
    assert kwargs['left'] == '20'
    assert 'Обход' in kwargs['note']


async def test_bandwidth_threshold_regular_note_without_bypass(monkeypatch):
    monkeypatch.setattr('app.utils.notification_prefs.is_traffic_warning_enabled', lambda user: True)
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', BYPASS)
    svc = _service()
    subscription = SimpleNamespace(traffic_limit_gb=50, traffic_used_gb=45.5, connected_squads=['other'])

    await svc._handle_bandwidth_threshold(
        None, _user(), subscription, {'lastTriggeredThreshold': 90, 'usedTrafficBytes': str(45 * 1024**3)}
    )

    kwargs = svc._notify_user.await_args.kwargs['format_kwargs']
    assert kwargs['left'] == '5'
    assert 'Обход' not in kwargs['note']


def test_threshold_text_formats_in_ru_and_en():
    for lang in ('ru', 'en'):
        text = _locale(lang)['WEBHOOK_SUB_BANDWIDTH_THRESHOLD']
        assert text.format(percent='80', left='20', note=' x', tariff_label='')


# ==================== тихие часы ====================


async def test_followups_skip_quiet_hours(monkeypatch):
    from app.services import monitoring_service as ms

    svc = ms.MonitoringService.__new__(ms.MonitoringService)
    svc.bot = MagicMock()
    monkeypatch.setattr(ms.NotificationSettingsService, 'are_notifications_globally_enabled', lambda: True)
    monkeypatch.setattr(ms.NotificationSettingsService, 'is_expired_1d_enabled', lambda: True)
    monkeypatch.setattr('app.services.user_reminders.dispatcher.is_quiet_time', lambda *a, **k: True)
    db = MagicMock()
    db.execute = AsyncMock()

    await svc._check_expired_subscription_followups(db)

    db.execute.assert_not_awaited()


# ==================== пробный с обходами ====================


def _trial(**kw):
    base = dict(
        id=7,
        user_id=1,
        status=SubscriptionStatus.ACTIVE.value,
        is_trial=True,
        end_date=datetime.now(UTC) + timedelta(days=2),
        traffic_limit_gb=5,
        traffic_used_gb=5.0,
        connected_squads=[BYPASS],
        bypass_suspended_at=None,
        grace_candidate_reason=None,
        grace_candidate_at=None,
        updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def bypass_on(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_DOWNGRADE_MODE', 'true')
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', BYPASS)
    monkeypatch.setattr(settings, 'BYPASS_OFF_SQUAD_UUID', OFF)


def test_trial_needs_the_include_trial_switch(bypass_on, monkeypatch):
    user = SimpleNamespace(status='active')
    monkeypatch.setattr(settings, 'BYPASS_INCLUDE_TRIAL', False)
    assert rules.ineligibility_reason(user, _trial()) == 'trial'
    monkeypatch.setattr(settings, 'BYPASS_INCLUDE_TRIAL', True)
    assert rules.ineligibility_reason(user, _trial()) is None


def test_bypass_quota_flag():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, 'BYPASS_SQUAD_UUID', BYPASS)
        assert rules.has_bypass_quota(_trial())
        assert not rules.has_bypass_quota(_trial(traffic_limit_gb=0))
        assert not rules.has_bypass_quota(_trial(connected_squads=['regular']))


async def test_trial_suspension_sends_trial_text(bypass_on, monkeypatch):
    from app.services.bypass_downgrade_service import BypassDowngradeService

    monkeypatch.setattr(settings, 'BYPASS_INCLUDE_TRIAL', True)
    svc = BypassDowngradeService()
    svc._push = AsyncMock(return_value=True)
    svc.notify = AsyncMock()
    svc._load_tariff = AsyncMock(return_value=None)
    db = MagicMock()
    db.commit = AsyncMock()

    assert await svc.handle_limited_webhook(db, SimpleNamespace(status='active'), _trial(), {})

    assert svc.notify.await_args.args[1] == 'BYPASS_SUSPENDED_TRIAL'


def test_trial_texts_explain_unlimited_regular_servers():
    for lang in ('ru', 'en'):
        d = _locale(lang)
        assert d['TRIAL_AVAILABLE_BYPASS_LINE'].format(gb=5)
        assert d['TRIAL_ACTIVATED_BYPASS_NOTE'].format(gb=5)
        assert d['SUBSCRIPTION_TRAFFIC_BYPASS_QUOTA'].format(used='1.0', limit=5)


# ==================== устройства ====================


def _pagination():
    return SimpleNamespace(page=1, total_pages=1, prev_page=None, next_page=None, has_prev=False, has_next=False)


def test_device_rows_use_disconnect_icon_and_add_slot_button():
    from app.keyboards.inline import get_devices_management_keyboard

    devices = [{'platform': 'iOS', 'deviceModel': 'iPhone 15', 'hwid': 'x'}]
    markup = get_devices_management_keyboard(
        devices, _pagination(), 'ru', add_slot_callback='subscription_change_devices'
    )

    texts = [b.text for row in markup.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert any(t.startswith('🗑') and 'iPhone' in t for t in texts)
    assert not any(t.startswith('🔄') and 'iPhone' in t for t in texts)
    assert 'subscription_change_devices' in callbacks


def test_no_add_slot_button_by_default():
    from app.keyboards.inline import get_devices_management_keyboard

    markup = get_devices_management_keyboard([], _pagination(), 'ru')
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert 'subscription_change_devices' not in callbacks


@pytest.mark.parametrize(
    ('limit', 'connected', 'trial', 'expected'),
    [(3, 3, False, True), (3, 2, False, False), (3, 3, True, False), (0, 5, False, False)],
)
def test_all_slots_taken(monkeypatch, limit, connected, trial, expected):
    from app.handlers.subscription import devices

    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)
    monkeypatch.setattr(settings, 'DEVICES_SELECTION_ENABLED', True)
    user = SimpleNamespace(subscription=SimpleNamespace(id=1, device_limit=limit, is_trial=trial))

    assert devices._all_device_slots_taken(user, None, connected) is expected
