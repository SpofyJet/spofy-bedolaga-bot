from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.wheel_service import FortuneWheelService


def _sub(sid, *, active=True):
    return SimpleNamespace(
        id=sid,
        is_active=active,
        wheel_bonus_devices=1,
        wheel_bonus_devices_until=datetime.now(UTC) - timedelta(minutes=1),
    )


def _wire(monkeypatch, subs, pushed):
    by_id = {s.id: s for s in subs}
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    seen = []

    async def execute(stmt):
        result = MagicMock()
        if not seen:
            seen.append(stmt)
            result.scalars.return_value.all.return_value = list(subs)
        else:
            sid = next(v for v in stmt.compile().params.values() if v in by_id)
            result.scalar_one_or_none.return_value = by_id[sid]
        return result

    db.execute = execute
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=db)
    session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr('app.database.database.AsyncSessionLocal', lambda: session)
    service = SimpleNamespace(update_remnawave_user=AsyncMock(return_value=pushed))
    monkeypatch.setattr('app.services.wheel_service.SubscriptionService', lambda: service)
    return db, service


async def test_pushed_bonus_is_cleared(monkeypatch):
    sub = _sub(5)
    _db, service = _wire(monkeypatch, [sub], pushed=object())

    assert await FortuneWheelService().expire_bonus_devices() == 1

    service.update_remnawave_user.assert_awaited_once()
    assert sub.wheel_bonus_devices == 0
    assert sub.wheel_bonus_devices_until is None


async def test_expired_subscription_keeps_the_bonus_while_the_panel_still_has_it(monkeypatch):
    sub = _sub(5, active=False)
    _db, service = _wire(monkeypatch, [sub], pushed=object())

    assert await FortuneWheelService().expire_bonus_devices() == 0

    service.update_remnawave_user.assert_not_awaited()
    assert sub.wheel_bonus_devices == 1


async def test_failed_push_keeps_the_bonus_for_the_next_round(monkeypatch):
    sub = _sub(5)
    db, _service = _wire(monkeypatch, [sub], pushed=None)

    assert await FortuneWheelService().expire_bonus_devices() == 0

    db.rollback.assert_awaited_once()
    assert sub.wheel_bonus_devices == 1
