"""Тесты лога действий юзера в кабинете (user_action_log_service)."""

from unittest.mock import patch

from app.config import Settings, settings
from app.services.user_action_log_service import (
    normalize_cabinet_path,
    schedule_cabinet_action_log,
    should_log_cabinet_action,
)


def test_defaults() -> None:
    assert Settings.model_fields['USER_ACTION_LOG_ENABLED'].default is True
    assert Settings.model_fields['USER_ACTION_LOG_RETENTION_DAYS'].default == 90


def test_normalize_cabinet_path() -> None:
    assert normalize_cabinet_path('/cabinet/subscriptions/5/renew') == '/cabinet/subscriptions/{id}/renew'
    assert normalize_cabinet_path('/cabinet/tickets/123') == '/cabinet/tickets/{id}'
    assert normalize_cabinet_path('/cabinet/balance/topup') == '/cabinet/balance/topup'


def test_should_log_gates(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'USER_ACTION_LOG_ENABLED', True, raising=False)

    assert should_log_cabinet_action('POST', '/cabinet/subscription/trial') is True
    assert should_log_cabinet_action('delete', '/cabinet/devices/1') is True
    # GET — не «кнопка», шум
    assert should_log_cabinet_action('GET', '/cabinet/subscription') is False
    # Админские действия уже пишутся в admin_audit_log
    assert should_log_cabinet_action('POST', '/cabinet/admin/users/1/balance') is False
    # Фоновый обмен токенов
    assert should_log_cabinet_action('POST', '/cabinet/auth/refresh') is False

    monkeypatch.setattr(settings, 'USER_ACTION_LOG_ENABLED', False, raising=False)
    assert should_log_cabinet_action('POST', '/cabinet/subscription/trial') is False


def test_schedule_skips_when_gated(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'USER_ACTION_LOG_ENABLED', True, raising=False)
    with patch('app.services.user_action_log_service.asyncio.create_task') as create_task:
        schedule_cabinet_action_log(1, 'GET', '/cabinet/subscription')
        create_task.assert_not_called()

        schedule_cabinet_action_log(1, 'POST', '/cabinet/subscription/trial')
        create_task.assert_called_once()
        # Извлекаем корутину, чтобы не ругался warning про не-awaited
        create_task.call_args.args[0].close()
