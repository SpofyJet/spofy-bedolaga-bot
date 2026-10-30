"""Подтверждение входа по webauth показывает, откуда запрошен вход."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services import web_auth_service


@pytest.mark.asyncio
async def test_token_stores_requester_and_context_is_read_without_consuming(monkeypatch) -> None:
    stored: dict = {}

    async def fake_set(key, value, expire=None):
        stored[key] = value
        return True

    monkeypatch.setattr(web_auth_service.cache, 'set', fake_set)
    monkeypatch.setattr(web_auth_service.cache, 'get', AsyncMock(side_effect=lambda key: stored.get(key)))
    getdel = AsyncMock()
    monkeypatch.setattr(web_auth_service.cache, 'getdel', getdel)

    token = await web_auth_service.create_web_auth_token(requester_ip='198.51.100.4', requester_agent='Firefox' * 40)
    context = await web_auth_service.get_web_auth_request_context(token)

    assert context['ip'] == '198.51.100.4'
    assert len(context['agent']) == 120
    getdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_context_for_linked_or_missing_token(monkeypatch) -> None:
    monkeypatch.setattr(web_auth_service.cache, 'get', AsyncMock(return_value={'status': 'linked'}))
    assert await web_auth_service.get_web_auth_request_context('t' * 32) is None
    monkeypatch.setattr(web_auth_service.cache, 'get', AsyncMock(return_value=None))
    assert await web_auth_service.get_web_auth_request_context('t' * 32) is None
