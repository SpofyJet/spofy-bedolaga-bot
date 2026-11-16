"""«Автопродление не прошло» и «истекает через 3 дня» больше не приходят вместе.

Цикл мониторинга сначала пробует автопродление (денег нет — «Автопродление не прошло» с суммой
и кнопкой пополнения), а следом шлёт напоминание о сроке той же подписки. По аудиту так
получали два сообщения подряд 33 человека из 79. Теперь в те же сутки второе не уходит.
Код цикла настоящий, база — SQLite, Redis «лежит» (отметка живёт в памяти процесса).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.monitoring_service as monitoring_module
from app.config import settings
from app.database.crud.notification import notification_sent
from app.database.models import Tariff
from tests.fixtures.sqlite_memory import memory_session
from tests.services.test_monitoring_warning_dedupe import TABLES, _service, _subscription, _user


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.services.notification_settings_service import NotificationSettingsService

    monkeypatch.setattr(NotificationSettingsService, 'are_notifications_globally_enabled', staticmethod(lambda: True))
    monkeypatch.setattr('app.utils.quiet_hours.is_quiet_time', lambda *a, **kw: False)
    monkeypatch.setattr(monitoring_module.cache, 'get', AsyncMock(return_value=None))
    monkeypatch.setattr(monitoring_module.cache, 'set', AsyncMock(return_value=False))
    monkeypatch.setattr(monitoring_module.cache, 'exists', AsyncMock(return_value=False))
    monkeypatch.setattr(settings, 'AUTOPAY_WARNING_DAYS', '3,1')


async def _seed(db, *, autopay: bool) -> None:
    db.add_all(
        [
            Tariff(
                id=2,
                name='Стандартный',
                is_active=True,
                traffic_limit_gb=0,
                device_limit=1,
                period_prices={'30': 15900},
                allowed_squads=[],
            ),
            _user(1, balance_kopeks=0),
            _subscription(
                10,
                1,
                tariff_id=2,
                autopay_enabled=autopay,
                autopay_days_before=3,
                end_date=datetime.now(UTC) + timedelta(days=2, hours=12),
            ),
        ]
    )
    await db.commit()


def _texts(service) -> list[str]:
    return [call.kwargs['text'] for call in service._send_message_with_logo.await_args_list]


@pytest.mark.asyncio
async def test_failed_autopay_and_expiry_reminder_come_as_one_message(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, autopay=True)
        service = _service(SimpleNamespace())
        service._send_message_with_logo = AsyncMock()
        service._log_monitoring_event = AsyncMock()

        await service._process_autopayments(db)
        await service._check_expiring_subscriptions(db)
        # Следующий цикл через несколько минут — тоже тишина.
        await service._process_autopayments(db)
        await service._check_expiring_subscriptions(db)
        covered = await notification_sent(db, 1, 10, 'expiring', 3)

    texts = _texts(service)
    assert len(texts) == 1, texts
    assert '159' in texts[0], 'осталось сообщение о неудачном автопродлении — с суммой'
    assert covered, 'порог «3 дня» закрыт, напоминание не догонит позже'


@pytest.mark.asyncio
async def test_expiry_reminder_still_goes_when_the_failure_notice_was_not_delivered(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, autopay=True)
        service = _service(SimpleNamespace())
        service._send_message_with_logo = AsyncMock()
        service._log_monitoring_event = AsyncMock()
        service._send_autopay_failed_notification = AsyncMock(return_value=False)  # сеть Telegram упала

        await service._process_autopayments(db)
        await service._check_expiring_subscriptions(db)

    assert len(_texts(service)) == 1, 'напоминание о сроке — единственное, что дошло'


@pytest.mark.asyncio
async def test_without_autopay_the_expiry_reminder_is_unchanged(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, autopay=False)
        service = _service(SimpleNamespace())
        service._send_message_with_logo = AsyncMock()
        service._log_monitoring_event = AsyncMock()

        await service._process_autopayments(db)
        await service._check_expiring_subscriptions(db)

    texts = _texts(service)
    assert len(texts) == 1 and 'закончится через 3 дня' in texts[0]
