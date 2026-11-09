"""Автопродление, которое молча не сработает: тариф отключён, цена не считается,
у периода нет цены. Напоминание обещало «ничего делать не нужно» — теперь человек
один раз получает «не получилось продлить автоматически» с кнопкой «Продлить».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.database.models import Base, Subscription, SubscriptionStatus, Tariff, User
from app.services.notification_settings_service import NotificationSettingsService
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


@pytest.fixture(autouse=True)
def tariffs_mode(monkeypatch):
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', True)
    monkeypatch.setattr(settings, 'DEFAULT_AUTOPAY_PERIOD_DAYS', 0)
    monkeypatch.setattr(NotificationSettingsService, 'are_notifications_globally_enabled', staticmethod(lambda: True))


def _rows(*, period_prices: dict, tariff_active: bool = True, balance_kopeks: int = 100000) -> list:
    now = datetime.now(UTC)
    return [
        User(
            id=1,
            telegram_id=1001,
            first_name='U',
            language='ru',
            status='active',
            balance_kopeks=balance_kopeks,
            remnawave_id=9001,
        ),
        Tariff(
            id=1,
            name='Старый',
            description='',
            is_active=tariff_active,
            is_daily=False,
            period_prices=period_prices,
            traffic_limit_gb=100,
            device_limit=1,
            allowed_squads=['squad-1'],
            display_order=1,
        ),
        Subscription(
            id=10,
            remnawave_short_id='s10',
            remnawave_id=9001,
            user_id=1,
            status=SubscriptionStatus.ACTIVE.value,
            is_trial=False,
            start_date=now - timedelta(days=29),
            end_date=now + timedelta(hours=6),
            traffic_limit_gb=100,
            traffic_used_gb=0.0,
            device_limit=1,
            tariff_id=1,
            connected_squads=['squad-1'],
            autopay_enabled=True,
            autopay_days_before=3,
            autopay_period_days=30,
        ),
    ]


def _service():
    import app.services.monitoring_service as monitoring_module

    service = monitoring_module.MonitoringService.__new__(monitoring_module.MonitoringService)
    service.bot = SimpleNamespace()
    service._notified_users = set()
    service._autopay_fail_state = {}
    service.subscription_service = SimpleNamespace(update_remnawave_user=AsyncMock(return_value=None))
    service._send_message_with_logo = AsyncMock()
    return service


async def _run_cycles(db, monkeypatch, rows, *, cycles: int = 2):
    import app.services.subscription_renewal_service as renewal_module

    monkeypatch.setattr(renewal_module, 'with_admin_notification_service', AsyncMock(return_value=None))
    db.add_all(rows)
    await db.commit()
    before = (await db.get(Subscription, 10)).end_date
    service = _service()
    for _ in range(cycles):
        await service._process_autopayments(db)
    subscription = await db.get(Subscription, 10)
    await db.refresh(subscription)
    return service, before, subscription


def _extend_callbacks(service) -> list[str]:
    markup = service._send_message_with_logo.await_args.kwargs['reply_markup']
    return [button.callback_data for row in markup.inline_keyboard for button in row]


@pytest.mark.asyncio
async def test_inactive_tariff_tells_user_once(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        service, before, subscription = await _run_cycles(
            db, monkeypatch, _rows(period_prices={'30': 20000}, tariff_active=False)
        )

    assert subscription.end_date == before  # не продлили и не списали
    service._send_message_with_logo.assert_awaited_once()
    text = service._send_message_with_logo.await_args.kwargs['text']
    assert 'Не получилось продлить подписку' in text
    assert 'автоматически' in text
    assert _extend_callbacks(service) in (['se:10'], ['subscription_extend'])


@pytest.mark.asyncio
async def test_unpriced_period_tells_user_once(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        service, before, subscription = await _run_cycles(db, monkeypatch, _rows(period_prices={'30': None}))

    assert subscription.end_date == before
    service._send_message_with_logo.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_error_tells_user_once_and_cycle_survives(monkeypatch):
    from app.services.pricing_engine import pricing_engine

    async with memory_session(monkeypatch, TABLES) as db:
        with patch.object(pricing_engine, 'calculate_renewal_price', AsyncMock(side_effect=RuntimeError('boom'))):
            service, before, subscription = await _run_cycles(db, monkeypatch, _rows(period_prices={'30': 20000}))

    assert subscription.end_date == before
    service._send_message_with_logo.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_balance_keeps_its_own_notice(monkeypatch):
    """Нехватка денег — штатный путь (свой текст «пополните»), новое сообщение не шлём."""
    async with memory_session(monkeypatch, TABLES) as db:
        service, before, _ = await _run_cycles(
            db, monkeypatch, _rows(period_prices={'30': 20000}, balance_kopeks=0), cycles=1
        )

    for call in service._send_message_with_logo.await_args_list:
        assert 'Не получилось продлить подписку' not in call.kwargs['text']


@pytest.mark.asyncio
async def test_guard_reports_inactive_tariff_but_wrapper_keeps_contract(monkeypatch):
    from app.services.autopay_guard import (
        lock_autopay_target,
        lock_autopay_target_checked,
    )

    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(_rows(period_prices={'30': 20000}, tariff_active=False))
        await db.commit()
        end = (await db.get(Subscription, 10)).end_date

        checked = await lock_autopay_target_checked(db, 1, 10, expected_end_date=end)
        assert checked.skip_reason == 'tariff_inactive'
        assert checked.subscription.id == 10
        assert await lock_autopay_target(db, 1, 10, expected_end_date=end) is None

        # Ручное продление между выборкой и блокировкой — штатный пропуск, без «тариф отключён».
        stale = await lock_autopay_target_checked(db, 1, 10, expected_end_date=end - timedelta(days=1))
        assert stale.skip_reason == 'not_eligible'


@pytest.mark.parametrize('lang', ['ru', 'en'])
def test_locale_has_cannot_renew_texts(lang):
    import json
    from pathlib import Path

    data = json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))
    text = data['AUTOPAY_CANNOT_RENEW']
    assert '{end_date}' in text and '{tariff_label}' in text
    assert data['AUTOPAY_CANNOT_RENEW_REASON']
