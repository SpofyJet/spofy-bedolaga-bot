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


async def test_unknown_code_is_answered_and_counts_as_a_guess(env):
    """Раньше параметр уходил в реферальную ветку: «Вы уже зарегистрированы… реферальная ссылка…»."""
    env.valid.return_value = {'valid': False, 'error': 'not_found'}
    message = _message()
    assert await link.claim_promo_link(message, env.state, None, None, 'promo_NOPE') is True
    env.failed.assert_called_once()
    assert 'Неверный промокод' in message.answer.await_args.args[0]


@pytest.mark.parametrize(('error', 'expected'), [('expired', 'истек'), ('used', 'уже использован')])
async def test_expired_or_exhausted_code_is_named(env, error, expected):
    env.valid.return_value = {'valid': False, 'error': error}
    user = SimpleNamespace(id=7, language='ru')
    for who in (user, None):  # и зарегистрированному, и новому до регистрации
        message = _message()
        assert await link.claim_promo_link(message, env.state, who, None, 'promo_OLD-1') is True
        assert expected in message.answer.await_args.args[0]
    env.failed.assert_not_called()
    env.activate.assert_not_awaited()
    env.state.update_data.assert_not_awaited()


async def test_campaign_named_promo_is_not_counted_as_a_guess(env):
    env.valid.return_value = {'valid': False, 'error': 'not_found'}
    env.campaign.return_value = object()
    message = _message()
    assert await link.claim_promo_link(message, env.state, None, None, 'promo_summer') is False
    env.failed.assert_not_called()
    message.answer.assert_not_awaited()


async def test_blocked_guesser_gets_no_oracle(env, monkeypatch):
    monkeypatch.setattr(promo_limiter, 'is_blocked', lambda _id: True)
    message = _message()
    assert await link.claim_promo_link(message, env.state, None, None, 'promo_ABC-123') is True
    env.valid.assert_not_awaited()
    assert 'Слишком много попыток' in message.answer.await_args.args[0]


async def test_bad_format_is_not_checked_but_answered(env):
    message = _message()
    assert await link.claim_promo_link(message, env.state, None, None, 'promo_a b!') is True
    env.valid.assert_not_awaited()
    assert 'Неверный промокод' in message.answer.await_args.args[0]


async def test_several_subscriptions_offer_the_choice_instead_of_invalid(env):
    """Раньше валидный код на дни при нескольких подписках показывался как «❌ Неверный промокод»."""
    env.activate.return_value = {
        'success': False,
        'error': 'select_subscription',
        'code': 'DAYS-7',
        'eligible_subscriptions': [
            {'id': 11, 'tariff_name': 'Стандарт', 'days_left': 5},
            {'id': 12, 'tariff_name': 'ULTIMA', 'days_left': 40},
        ],
    }
    message = _message()
    assert await link.claim_promo_link(message, env.state, SimpleNamespace(id=7, language='ru'), None, 'promo_DAYS-7')
    text = message.answer.await_args.args[0]
    assert 'Неверный' not in text and 'К какой подписке' in text
    callbacks = [
        b.callback_data for row in message.answer.await_args.kwargs['reply_markup'].inline_keyboard for b in row
    ]
    assert callbacks == ['promo_sub:11:DAYS-7', 'promo_sub:12:DAYS-7', 'back_to_menu']
