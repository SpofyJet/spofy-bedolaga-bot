"""Автовыдача промогруппы не должна оставлять блокировку строки пользователя."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import promo_group_assignment as assignment


def _db() -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=1, telegram_id=1))
    return db


async def test_no_lock_when_no_group_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    lock = AsyncMock()
    monkeypatch.setattr(assignment, 'lock_user_for_update', lock)
    monkeypatch.setattr(assignment, 'get_user_total_spent_kopeks', AsyncMock(return_value=100))
    monkeypatch.setattr(assignment, '_get_best_group_for_spending', AsyncMock(return_value=None))

    assert await assignment.maybe_assign_promo_group_by_total_spent(_db(), 1) is None
    lock.assert_not_awaited()


async def test_no_lock_without_spending(monkeypatch: pytest.MonkeyPatch) -> None:
    lock = AsyncMock()
    monkeypatch.setattr(assignment, 'lock_user_for_update', lock)
    monkeypatch.setattr(assignment, 'get_user_total_spent_kopeks', AsyncMock(return_value=0))

    assert await assignment.maybe_assign_promo_group_by_total_spent(_db(), 1) is None
    lock.assert_not_awaited()


async def test_lock_is_released_if_group_disappears_after_locking(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    user = SimpleNamespace(
        id=1, telegram_id=1, auto_promo_group_threshold_kopeks=0, get_primary_promo_group=lambda: None
    )
    monkeypatch.setattr(assignment, 'lock_user_for_update', AsyncMock(return_value=user))
    monkeypatch.setattr(assignment, 'get_user_total_spent_kopeks', AsyncMock(return_value=100))
    monkeypatch.setattr(
        assignment, '_get_best_group_for_spending', AsyncMock(side_effect=[SimpleNamespace(id=7), None])
    )

    assert await assignment.maybe_assign_promo_group_by_total_spent(db, 1) is None
    db.commit.assert_awaited_once()
