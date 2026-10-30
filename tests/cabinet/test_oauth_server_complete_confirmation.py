"""Привязка соцсети через server-complete требует подтверждения владельца.

server-complete авторизуется только state-токеном, привязанным к инициатору,
но не к браузеру. Атакующий брал authorize_url со своим state и отправлял жертве:
жертва входила в Google, и колбэк молча привязывал её Google к аккаунту
атакующего (с переносом её почты как подтверждённой). Теперь колбэк сначала
показывает, к какому аккаунту идёт привязка (preview), завершение возможно
только с confirm=true, а почта провайдера в этом потоке не переносится.
"""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.cabinet.routes import account_linking


_STATE = {'provider': 'google', 'linking': 'true', 'user_id': '7'}


def _attacker() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        first_name='Иван',
        username='ivan_attacker',
        email=None,
        email_verified=False,
        telegram_id=123456789,
        google_id=None,
    )


def _patches(stack: ExitStack, user, *, state=_STATE, provider_email='victim@gmail.com'):
    prov = MagicMock()
    prov.exchange_code = AsyncMock(return_value={'access_token': 'x'})
    prov.get_user_info = AsyncMock(
        return_value=SimpleNamespace(provider_id='G-victim', email=provider_email, email_verified=True)
    )
    validate = AsyncMock(return_value=dict(state))
    stack.enter_context(patch.object(account_linking, 'validate_oauth_state', validate))
    stack.enter_context(patch.object(account_linking, 'peek_oauth_state', AsyncMock(return_value=dict(state))))
    stack.enter_context(patch.object(account_linking, 'get_user_by_id', AsyncMock(return_value=user)))
    stack.enter_context(patch.object(account_linking, 'get_provider', MagicMock(return_value=prov)))
    stack.enter_context(patch.object(account_linking, 'get_user_by_oauth_provider', AsyncMock(return_value=None)))
    stack.enter_context(patch.object(account_linking, 'get_user_by_email', AsyncMock(return_value=None)))
    stack.enter_context(
        patch.object(account_linking.RateLimitCache, 'is_ip_rate_limited', AsyncMock(return_value=False))
    )
    stack.enter_context(patch.object(account_linking, 'get_client_ip', MagicMock(return_value='1.2.3.4')))
    set_id = AsyncMock()
    stack.enter_context(patch.object(account_linking, 'set_user_oauth_provider_id', set_id))
    return validate, set_id


@pytest.mark.asyncio
async def test_server_complete_without_confirmation_is_rejected_and_keeps_state() -> None:
    user = _attacker()
    with ExitStack() as stack:
        validate, set_id = _patches(stack, user)
        with pytest.raises(HTTPException) as exc:
            await account_linking.link_server_complete(
                account_linking.ServerCompleteRequest(code='c', state='s'), MagicMock(), db=AsyncMock()
            )

    assert exc.value.status_code == 400
    validate.assert_not_awaited()  # state не сгорает от автоматического запроса
    set_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_server_complete_links_without_email_backfill() -> None:
    user = _attacker()
    with ExitStack() as stack:
        _, set_id = _patches(stack, user)
        result = await account_linking.link_server_complete(
            account_linking.ServerCompleteRequest(code='c', state='s', confirm=True), MagicMock(), db=AsyncMock()
        )

    assert result.success is True
    assert result.provider == 'google'
    set_id.assert_awaited_once()
    assert user.email is None, 'почта жертвы не должна оседать на аккаунте из state'
    assert user.email_verified is False


@pytest.mark.asyncio
async def test_preview_shows_masked_target_account_without_consuming_state() -> None:
    user = _attacker()
    with ExitStack() as stack:
        validate, _ = _patches(stack, user)
        preview = await account_linking.link_server_complete_preview('s', MagicMock(), db=AsyncMock())

    assert preview.provider == 'google'
    assert 'Иван' in preview.account_label
    assert '@iv***' in preview.account_label
    assert 'ivan_attacker' not in preview.account_label
    assert '123456789' not in preview.account_label
    validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_rejects_login_state() -> None:
    with ExitStack() as stack:
        _patches(stack, _attacker(), state={'provider': 'google'})
        with pytest.raises(HTTPException) as exc:
            await account_linking.link_server_complete_preview('s', MagicMock(), db=AsyncMock())

    assert exc.value.status_code == 400
