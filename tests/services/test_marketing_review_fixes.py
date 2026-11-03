"""Правки по маркетинговому разбору 2026-11-03: тексты и решения, на которые легко наступить снова."""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.handlers.subscription.tariff_purchase import tariff_has_bypass_quota, tariff_traffic_text
from app.localization.texts import get_texts
from app.services import remnawave_webhook_service as webhook
from app.services.monitoring_service import traffic_warning_cache_key
from app.services.payment.common import topup_success_text


def test_topup_message_says_amount_and_new_balance_without_transaction_id():
    user = SimpleNamespace(language='ru', balance_kopeks=34900)
    text = topup_success_text(user, 19900)
    assert 'Зачислено 199' in text and 'Баланс: 349' in text
    assert 'Транзакция' not in text and '🦊' not in text


def test_topup_message_without_known_balance_has_no_balance_line():
    assert 'Баланс' not in topup_success_text(SimpleNamespace(language='ru'), 10000)


def test_bypass_tariff_is_not_shown_as_a_traffic_cap(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', 'bypass-squad')
    texts = get_texts('ru')
    bypass = SimpleNamespace(allowed_squads=['main', 'bypass-squad'], traffic_limit_gb=50)
    plain = SimpleNamespace(allowed_squads=['main'], traffic_limit_gb=50)
    assert tariff_has_bypass_quota(bypass) and not tariff_has_bypass_quota(plain)
    assert tariff_traffic_text(bypass, texts) == '∞ + 50 ГБ обходов'
    assert tariff_traffic_text(plain, texts) != '∞ + 50 ГБ обходов'


def test_traffic_warning_key_changes_with_limit():
    # Докупка или новый период меняют лимит — предупреждение про новый лимит снова возможно.
    assert traffic_warning_cache_key(7, 50) != traffic_warning_cache_key(7, 100)


@pytest.mark.parametrize(('kind', 'expired_1d', 'expected'), [('expiring', False, True), ('expired_1d', False, False)])
def test_panel_expiry_reminders_yield_to_bot(monkeypatch, kind, expired_1d, expected):
    from app.services.notification_settings_service import NotificationSettingsService

    monkeypatch.setattr(NotificationSettingsService, 'are_notifications_globally_enabled', classmethod(lambda cls: True))
    monkeypatch.setattr(NotificationSettingsService, 'is_expired_1d_enabled', classmethod(lambda cls: expired_1d))
    assert webhook._bot_sends_expiry_reminders(kind) is expected


def test_panel_reminders_are_fallback_when_bot_notifications_off(monkeypatch):
    from app.services.notification_settings_service import NotificationSettingsService

    monkeypatch.setattr(NotificationSettingsService, 'are_notifications_globally_enabled', classmethod(lambda cls: False))
    assert webhook._bot_sends_expiry_reminders('expiring') is False


def test_texts_follow_owner_terms():
    texts = get_texts('ru')
    assert 'обращение' in texts.t('CLOSE_TICKET', '')
    assert texts.t('RECURRENT_ENGINE_BALANCE', '') == 'с баланса'
    assert 'Недостаточно' not in texts.t('TARIFF_PURCHASE_INSUFFICIENT', '')
    assert 'пробный период' not in texts.t('SUBSCRIPTION_IMPORT_INSTRUCTION_PROMPT', '').lower()
    assert 'автоматически' not in texts.t('SUBSCRIPTION_EXPIRED_SECOND_WAVE', '')
