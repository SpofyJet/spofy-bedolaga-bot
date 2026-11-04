"""Пользователь кабинета не мог закрыть своё обращение: в боте кнопка есть, в кабинете
не было ни роута, ни кнопки. ``POST /tickets/{id}/close`` закрывает только своё обращение."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.cabinet.routes import tickets as tickets_route
from app.database.models import Ticket, User


@pytest.fixture(autouse=True)
def _tickets_enabled(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, 'SUPPORT_SYSTEM_MODE', 'both')


def _db_returning(ticket: Ticket | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = ticket
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.expire_all = MagicMock()
    return db


async def test_closes_own_open_ticket(monkeypatch) -> None:
    user = User(id=42, telegram_id=1)
    ticket = Ticket(id=7, user_id=42, status='answered')
    close = AsyncMock(return_value=True)
    detail = AsyncMock(return_value='detail')
    monkeypatch.setattr(tickets_route.TicketCRUD, 'close_ticket', close)
    monkeypatch.setattr(tickets_route, 'get_ticket', detail)

    db = _db_returning(ticket)
    assert await tickets_route.close_ticket(7, user=user, db=db) == 'detail'

    close.assert_awaited_once_with(db, 7)
    detail.assert_awaited_once_with(7, user=user, db=db)


async def test_already_closed_is_not_closed_again(monkeypatch) -> None:
    close = AsyncMock()
    monkeypatch.setattr(tickets_route.TicketCRUD, 'close_ticket', close)
    monkeypatch.setattr(tickets_route, 'get_ticket', AsyncMock(return_value='detail'))

    db = _db_returning(Ticket(id=7, user_id=42, status='closed'))
    assert await tickets_route.close_ticket(7, user=User(id=42, telegram_id=1), db=db) == 'detail'
    close.assert_not_awaited()


async def test_someone_elses_ticket_is_404(monkeypatch) -> None:
    close = AsyncMock()
    monkeypatch.setattr(tickets_route.TicketCRUD, 'close_ticket', close)

    # The query filters by user_id, so another user's ticket comes back as nothing.
    with pytest.raises(HTTPException) as exc:
        await tickets_route.close_ticket(7, user=User(id=43, telegram_id=2), db=_db_returning(None))
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND
    close.assert_not_awaited()
