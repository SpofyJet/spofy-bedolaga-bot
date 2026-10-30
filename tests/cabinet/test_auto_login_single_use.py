"""Токен автовхода со страницы покупки работает один раз."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.cabinet.routes import auth as auth_routes


@pytest.mark.asyncio
async def test_replayed_auto_login_token_is_rejected(monkeypatch) -> None:
    limiter = MagicMock()
    limiter.is_ip_rate_limited = AsyncMock(return_value=False)
    monkeypatch.setattr(auth_routes, 'RateLimitCache', limiter)
    monkeypatch.setattr(auth_routes, 'get_client_ip', lambda request: '203.0.113.7')
    monkeypatch.setattr(auth_routes, 'get_token_payload', lambda token, expected_type: {'sub': '42'})
    replay = MagicMock()
    replay.is_token_replayed = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_routes, 'TokenReplayCache', replay)
    get_user = AsyncMock()
    monkeypatch.setattr(auth_routes, 'get_user_by_id', get_user)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.auto_login(SimpleNamespace(token='jwt'), raw_request=None, db=AsyncMock())

    assert exc.value.status_code == 401
    get_user.assert_not_awaited()
    key = replay.is_token_replayed.await_args.args[0]
    assert key.startswith('auto_login:') and 'jwt' not in key
