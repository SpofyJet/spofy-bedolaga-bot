"""Spofy subpage: владелец подписки грузится тем же загрузчиком, что и в кабинете.

С одним selectinload(Subscription.user) у пользователя не были загружены промогруппы, и
на подписке мульти-тарифа расчёт цены продления (user.get_primary_promo_group()) лениво
подгружал promo_group внутри async-кода → sqlalchemy MissingGreenlet → 500 на offer
(2026-10-03, вторая подписка владельца).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.cabinet.routes import spofy_subpage as bridge


def _db_with(subscription):
    result = MagicMock()
    result.scalar_one_or_none.return_value = subscription
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


async def test_owner_comes_from_the_cabinet_user_loader(monkeypatch):
    lazy_user = SimpleNamespace(id=2, status='active')
    loaded_user = SimpleNamespace(id=2, status='active', promo_group=None)
    subscription = SimpleNamespace(id=11, user_id=2, user=lazy_user)
    loader = AsyncMock(return_value=loaded_user)
    monkeypatch.setattr(bridge, 'get_user_by_id', loader)

    user, sub = await bridge.resolve_owner(_db_with(subscription), 'ktPgYujCWP5yueZs')

    assert user is loaded_user and sub is subscription
    assert loader.await_args.args[1] == 2


async def test_blocked_owner_is_still_refused(monkeypatch):
    subscription = SimpleNamespace(id=11, user_id=2, user=SimpleNamespace(id=2))
    monkeypatch.setattr(bridge, 'get_user_by_id', AsyncMock(return_value=SimpleNamespace(id=2, status='blocked')))

    with pytest.raises(HTTPException) as error:
        await bridge.resolve_owner(_db_with(subscription), 'ktPgYujCWP5yueZs')
    assert error.value.status_code == 403
