"""Вход в miniapp считается после проверки подписи, а занятый пул отвечает 503."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.cabinet.routes import auth
from app.webapi.middleware import pool_exhausted_handler


def _patch(monkeypatch: pytest.MonkeyPatch, user_data: dict | None, limited: bool) -> AsyncMock:
    limiter = AsyncMock(return_value=limited)
    monkeypatch.setattr(auth.RateLimitCache, 'is_ip_rate_limited', limiter)
    monkeypatch.setattr(auth, 'validate_telegram_init_data', MagicMock(return_value=user_data))
    monkeypatch.setattr(auth, 'get_client_ip', MagicMock(return_value='10.0.0.1'))
    return limiter


async def _login() -> None:
    await auth.auth_telegram(SimpleNamespace(init_data='x', referral_code=None), MagicMock(), AsyncMock())


async def test_valid_signature_is_not_limited_by_shared_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = _patch(monkeypatch, {'id': 42}, limited=True)

    with pytest.raises(HTTPException) as error:
        await _login()

    assert error.value.status_code == 429
    assert limiter.await_args.args[0] == 'tg:42'
    assert limiter.await_count == 1


async def test_invalid_signature_is_limited_by_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = _patch(monkeypatch, None, limited=False)

    with pytest.raises(HTTPException) as error:
        await _login()

    assert error.value.status_code == 401
    assert limiter.await_args.args[0] == '10.0.0.1'


async def test_invalid_signature_over_limit_gets_429(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, None, limited=True)

    with pytest.raises(HTTPException) as error:
        await _login()

    assert error.value.status_code == 429


async def test_pool_exhausted_answers_503_with_pause() -> None:
    request = SimpleNamespace(method='GET', url=SimpleNamespace(path='/cabinet/auth/me'))

    response = await pool_exhausted_handler(request, SQLAlchemyTimeoutError('QueuePool limit'))

    assert response.status_code == 503
    assert response.headers['retry-after'] == '5'
    assert 'detail' in json.loads(response.body)
