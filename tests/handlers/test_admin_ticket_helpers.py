"""Общие проверки админских тикетов: доступ и запись в журнал поддержки."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.admin import tickets as admin_tickets


def _callback(user_id=777):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id), answer=AsyncMock())


def _staff(monkeypatch, *, admin: bool, moderator: bool):
    monkeypatch.setattr(type(admin_tickets.settings), 'is_admin', lambda self, uid: admin)
    monkeypatch.setattr(admin_tickets.SupportSettingsService, 'is_moderator', staticmethod(lambda uid: moderator))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('admin', 'moderator', 'denied'), [(True, False, False), (False, True, False), (False, False, True)]
)
async def test_deny_non_staff(monkeypatch, admin, moderator, denied):
    _staff(monkeypatch, admin=admin, moderator=moderator)
    callback = _callback()
    assert await admin_tickets._deny_non_staff(callback, SimpleNamespace(language='ru')) is denied
    assert callback.answer.await_count == int(denied)


@pytest.mark.asyncio
async def test_audit_carries_ticket_owner_contacts(monkeypatch):
    _staff(monkeypatch, admin=False, moderator=True)
    owner = SimpleNamespace(telegram_id=555, username='owner')
    monkeypatch.setattr(
        admin_tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=SimpleNamespace(user=owner))
    )
    audit = AsyncMock()
    monkeypatch.setattr(admin_tickets.TicketCRUD, 'add_support_audit', audit)

    await admin_tickets._audit_ticket_action(
        'db', _callback(), SimpleNamespace(id=3), 5, 'close_ticket', log_context='t'
    )

    audit.assert_awaited_once_with(
        'db',
        actor_user_id=3,
        actor_telegram_id=777,
        is_moderator=True,
        action='close_ticket',
        ticket_id=5,
        target_user_id=None,
        details={'target_telegram_id': 555, 'target_username': 'owner'},
    )


@pytest.mark.asyncio
async def test_audit_failure_is_swallowed(monkeypatch):
    _staff(monkeypatch, admin=True, moderator=False)
    monkeypatch.setattr(admin_tickets.TicketCRUD, 'get_ticket_by_id', AsyncMock(side_effect=RuntimeError('db')))
    audit = AsyncMock(side_effect=RuntimeError('audit'))
    monkeypatch.setattr(admin_tickets.TicketCRUD, 'add_support_audit', audit)

    await admin_tickets._audit_ticket_action('db', _callback(), None, 5, 'unblock_user', log_context='t')

    assert audit.await_args.kwargs['details'] == {}
    assert audit.await_args.kwargs['actor_user_id'] is None
