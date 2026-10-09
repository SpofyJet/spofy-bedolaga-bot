"""Ссылка с билета /start promo_<КОД>: код применяется сам и не открывает путь к перебору."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.crud import campaign as campaign_crud, promocode as promocode_crud
from app.handlers import promo_deeplink as link, promocode as promocode_handler
from app.utils.promo_rate_limiter import promo_limiter


def test_link_parsing():
    assert link.is_promo_deeplink('promo_SPOFY-AAAA-BBBB') and link.is_promo_deeplink('PROMO_x1')
    assert (
        not link.is_promo_deeplink('promo_')
        and not link.is_promo_deeplink('promotion')
        and not link.is_promo_deeplink(None)
    )
    assert link.promo_code_from('promo_SPOFY-AAAA-BBBB') == 'SPOFY-AAAA-BBBB'


def _message(user_id=501):
    message = MagicMock()
    message.from_user = SimpleNamespace(id=user_id)
    message.answer = AsyncMock()
    message.bot = MagicMock()
    return message


@pytest.fixture
def env(monkeypatch):
    promo_limiter.reset() if hasattr(promo_limiter, 'reset') else None
    state = MagicMock(update_data=AsyncMock())
    calls = SimpleNamespace(
        valid=AsyncMock(return_value={'valid': True}),
        activate=AsyncMock(return_value={'success': True, 'description': '730 дней'}),
        campaign=AsyncMock(return_value=None),
        state=state,
    )
    monkeypatch.setattr(promocode_crud, 'check_promocode_validity', calls.valid)
    monkeypatch.setattr(promocode_handler, 'activate_promocode_for_registration', calls.activate)
    monkeypatch.setattr(campaign_crud, 'get_campaign_by_start_parameter', calls.campaign)
    monkeypatch.setattr(promo_limiter, 'is_blocked', lambda _id: False)
    monkeypatch.setattr(promo_limiter, 'record_activation', MagicMock())
    calls.failed = MagicMock()
    monkeypatch.setattr(promo_limiter, 'record_failed_attempt', calls.failed)
    return calls


async def test_new_user_code_is_kept_for_registration(env):
    assert await link.claim_promo_link(_message(), env.state, None, None, 'promo_SPOFY-AAAA-BBBB') is True
    env.state.update_data.assert_awaited_once_with(promocode='SPOFY-AAAA-BBBB')
    env.activate.assert_not_awaited()


async def test_registered_user_gets_it_applied_now(env):
    user = SimpleNamespace(id=7, language='ru')
    message = _message()
    assert await link.claim_promo_link(message, env.state, user, None, 'promo_SPOFY-AAAA-BBBB') is True
    assert env.activate.await_args.args[1:3] == (7, 'SPOFY-AAAA-BBBB')
    assert '730 дней' in message.answer.await_args.args[0]


async def test_used_code_tells_the_person(env):
    env.activate.return_value = {'success': False, 'error': 'used'}
    message = _message()
    await link.claim_promo_link(message, env.state, SimpleNamespace(id=7, language='ru'), None, 'promo_ABC-123')
    assert message.answer.await_count == 1


async def test_unknown_code_falls_through_and_counts_as_a_guess(env):
    env.valid.return_value = {'valid': False}
    assert await link.claim_promo_link(_message(), env.state, None, None, 'promo_NOPE') is False
    env.failed.assert_called_once()


async def test_campaign_named_promo_is_not_counted_as_a_guess(env):
    env.valid.return_value = {'valid': False}
    env.campaign.return_value = object()
    assert await link.claim_promo_link(_message(), env.state, None, None, 'promo_summer') is False
    env.failed.assert_not_called()


async def test_blocked_guesser_is_ignored(env, monkeypatch):
    monkeypatch.setattr(promo_limiter, 'is_blocked', lambda _id: True)
    assert await link.claim_promo_link(_message(), env.state, None, None, 'promo_ABC-123') is False
    env.valid.assert_not_awaited()


async def test_bad_format_is_ignored(env):
    assert await link.claim_promo_link(_message(), env.state, None, None, 'promo_a b!') is False
    env.valid.assert_not_awaited()
