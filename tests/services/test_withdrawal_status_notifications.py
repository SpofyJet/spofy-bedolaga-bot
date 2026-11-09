"""Уведомления о решении по заявке на вывод: одни для бота и кабинета.

* отказ — с причиной, если она есть, и с кнопкой «Поддержка» (живёт в «Инфо»);
* «Выплата выполнена» из кабинета теперь тоже уведомляет человека.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types
from aiogram.enums import ChatType

import app.handlers.admin.referrals as admin_referrals
from app.cabinet.routes import admin_withdrawals
from app.config import Settings
from app.database.models import WithdrawalRequestStatus
from app.services import withdrawal_notifications
from app.services.support_settings_service import SupportSettingsService
from app.services.withdrawal_notifications import (
    DEFAULT_BOT_REJECT_COMMENT,
    build_withdrawal_status_message,
)


REJECTED = WithdrawalRequestStatus.REJECTED.value


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row] if markup else []


@pytest.fixture(autouse=True)
def support_menu_on(monkeypatch):
    monkeypatch.setattr(SupportSettingsService, 'is_support_menu_enabled', classmethod(lambda cls: True))


def test_rejection_without_reason_is_neutral_and_has_support_button():
    text, markup = build_withdrawal_status_message(
        'ru', request_id=5, amount_kopeks=50_000, status=REJECTED, comment=DEFAULT_BOT_REJECT_COMMENT
    )
    assert '#5' in text and 'отклонена' in text
    assert 'Причина' not in text
    assert DEFAULT_BOT_REJECT_COMMENT not in text
    assert _callbacks(markup) == ['menu_support']


def test_rejection_with_reason_shows_it_escaped():
    text, markup = build_withdrawal_status_message(
        'en', request_id=5, amount_kopeks=50_000, status=REJECTED, comment='Card <b>blocked</b>'
    )
    assert 'Reason: Card &lt;b&gt;blocked&lt;/b&gt;' in text
    assert _callbacks(markup) == ['menu_support']


def test_completed_has_no_support_button():
    text, markup = build_withdrawal_status_message(
        'ru', request_id=5, amount_kopeks=50_000, status=WithdrawalRequestStatus.COMPLETED.value
    )
    assert 'выполнена' in text
    assert markup is None


def _request():
    request = MagicMock()
    request.id = 5
    request.user_id = 42
    request.status = WithdrawalRequestStatus.PENDING.value
    request.amount_kopeks = 50_000
    request.payment_details = 'карта 1234'
    request.risk_analysis = None
    request.created_at = None
    return request


def _user():
    return SimpleNamespace(id=42, telegram_id=777, full_name='Автор', email=None, language='ru')


@pytest.mark.asyncio
async def test_bot_rejection_sends_support_button(monkeypatch):
    monkeypatch.setattr(Settings, 'is_admin', lambda self, user_id: True)
    request = _request()

    async def reject(db, request_id, admin_id, comment):
        request.status = REJECTED
        return True, None

    monkeypatch.setattr(admin_referrals.referral_withdrawal_service, 'reject_request', reject)
    monkeypatch.setattr(admin_referrals, 'get_user_by_id', AsyncMock(return_value=_user()))
    monkeypatch.setattr(admin_referrals, 'view_withdrawal_request', AsyncMock())
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: request))
    callback = MagicMock()
    callback.__class__ = types.CallbackQuery
    callback.data = 'admin_withdrawal_reject_5'
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.bot.send_message = AsyncMock()
    callback.message.chat.type = ChatType.PRIVATE

    await admin_referrals.reject_withdrawal_request(callback, _user(), db)

    callback.bot.send_message.assert_awaited_once()
    args, kwargs = callback.bot.send_message.await_args
    assert args[0] == 777
    assert 'Причина' not in args[1]
    assert _callbacks(kwargs['reply_markup']) == ['menu_support']


@pytest.mark.asyncio
async def test_cabinet_complete_notifies_user(monkeypatch):
    from app import bot_factory
    from app.config import settings

    monkeypatch.setattr(
        admin_withdrawals.referral_withdrawal_service, 'complete_request', AsyncMock(return_value=(True, None))
    )
    monkeypatch.setattr(settings, 'BOT_TOKEN', 'masked:token')
    bot = SimpleNamespace(send_message=AsyncMock(), session=SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(bot_factory, 'create_bot', lambda *a, **kw: bot)
    withdrawal = SimpleNamespace(id=5, user_id=42, amount_kopeks=50_000)
    user = _user()
    db = AsyncMock()
    db.get = AsyncMock(side_effect=lambda model, _id: withdrawal if model.__name__ == 'WithdrawalRequest' else user)

    result = await admin_withdrawals.complete_withdrawal(5, admin=SimpleNamespace(id=1), db=db)

    assert result == {'success': True}
    bot.send_message.assert_awaited_once()
    args, kwargs = bot.send_message.await_args
    assert args[0] == 777
    assert 'Выплата по заявке #5 выполнена' in args[1]
    bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_skips_users_without_telegram():
    bot = SimpleNamespace(send_message=AsyncMock())
    sent = await withdrawal_notifications.notify_user_about_withdrawal_status(
        bot,
        SimpleNamespace(telegram_id=None, language='ru'),
        request_id=1,
        amount_kopeks=100,
        status=REJECTED,
    )
    assert sent is False
    bot.send_message.assert_not_awaited()
