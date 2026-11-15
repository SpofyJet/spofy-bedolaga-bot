"""Получатели закреплённого сообщения: один сбор telegram_id для рассылки и для открепления."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import pinned_message_service as service


class _FreshSession:
    async def __aenter__(self):
        return 'fresh-db'

    async def __aexit__(self, *exc):
        return False


def _users(*telegram_ids):
    return [SimpleNamespace(telegram_id=tid) for tid in telegram_ids]


@pytest.mark.asyncio
async def test_collects_active_ids_in_batches_and_skips_email_only(monkeypatch):
    pages = [_users(*range(1, 5001)), _users(None, 9001, None), []]
    get_users = AsyncMock(side_effect=pages)
    monkeypatch.setattr(service, 'get_users_list', get_users)

    ids = await service._active_telegram_ids('db')

    assert ids == [*range(1, 5001), 9001]
    assert [call.kwargs['offset'] for call in get_users.await_args_list] == [0, 5000, 10000]
    assert {call.kwargs['status'] for call in get_users.await_args_list} == {service.UserStatus.ACTIVE}


@pytest.mark.asyncio
async def test_broadcast_and_unpin_reach_the_same_people(monkeypatch):
    monkeypatch.setattr(
        service, 'get_users_list', AsyncMock(side_effect=lambda db, **kw: [] if kw['offset'] else _users(5, None, 6))
    )
    sent, unpinned = [], []

    async def send(bot, chat_id, pinned):
        sent.append(chat_id)
        return True

    async def unpin(bot, chat_id):
        unpinned.append(chat_id)
        return True

    monkeypatch.setattr(service, '_send_and_pin_message', send)
    monkeypatch.setattr(service, '_unpin_message_for_user', unpin)
    monkeypatch.setattr(service, 'get_active_pinned_message', AsyncMock(return_value=SimpleNamespace(id=1)))
    deactivate = AsyncMock()
    monkeypatch.setattr(service, 'deactivate_active_pinned_message', deactivate)
    monkeypatch.setattr(service, 'AsyncSessionLocal', _FreshSession)

    assert await service.broadcast_pinned_message('bot', 'db', SimpleNamespace(id=1)) == (2, 0)
    unpin_result = await service.unpin_active_pinned_message('bot', 'db')

    assert sorted(sent) == sorted(unpinned) == [5, 6]
    assert unpin_result == (2, 0, True)
    deactivate.assert_awaited_once_with('fresh-db')
