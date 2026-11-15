"""Кабинет: включение и выключение автоплатежа с баланса (``update_autopay``)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.cabinet.routes.subscription_modules import autopay as route
from app.cabinet.schemas.subscription import AutopayUpdateRequest
from app.database.models import User


def _user() -> User:
    return User(id=1, telegram_id=123456)


def _subscription(**overrides) -> SimpleNamespace:
    base = dict(
        id=42,
        tariff_id=5,
        tariff=None,
        is_trial=False,
        autopay_enabled=False,
        autopay_days_before=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _resolve_to(monkeypatch, db, subscription) -> None:
    async def fake_resolve(resolve_db, u, subscription_id):
        assert resolve_db is db
        return subscription

    monkeypatch.setattr('app.cabinet.routes.subscription_modules.helpers.resolve_subscription', fake_resolve)


@pytest.mark.parametrize('enabled', [True, False])
async def test_update_autopay_saves_the_flag(monkeypatch, enabled):
    subscription = _subscription(autopay_enabled=not enabled)
    db = AsyncMock()
    _resolve_to(monkeypatch, db, subscription)

    result = await route.update_autopay(
        AutopayUpdateRequest(enabled=enabled), user=_user(), db=db, subscription_id=None
    )

    assert result['autopay_enabled'] is enabled
    db.commit.assert_awaited_once()


async def test_enable_autopay_rejected_for_trial(monkeypatch):
    subscription = _subscription(is_trial=True)
    db = AsyncMock()
    _resolve_to(monkeypatch, db, subscription)

    with pytest.raises(HTTPException) as exc:
        await route.update_autopay(AutopayUpdateRequest(enabled=True), user=_user(), db=db, subscription_id=None)

    assert exc.value.status_code == 400
    db.commit.assert_not_awaited()
