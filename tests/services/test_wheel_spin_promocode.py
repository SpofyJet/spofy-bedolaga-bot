"""Промокод на спин колеса: только для активной платной подписки."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.database.crud import promocode as promo_crud, wheel as wheel_crud
from app.database.models import PromoCodeType, Subscription, SubscriptionStatus
from app.handlers.promocode import promocode_error_text, wheel_spin_keyboard
from app.services import promocode_service as module


def _subscription(status=SubscriptionStatus.ACTIVE.value, *, trial=False, days=10):
    return Subscription(status=status, is_trial=trial, end_date=datetime.now(UTC) + timedelta(days=days))


def _code():
    return SimpleNamespace(
        id=9, code='SPIN', type=PromoCodeType.WHEEL_SPIN.value, is_valid=True, first_purchase_only=False,
        balance_bonus_kopeks=0, subscription_days=0, traffic_gb=0, tariff_id=None, promo_group_id=None,
        max_uses=500, current_uses=0, valid_until=None,
    )  # fmt: skip


@pytest.fixture
def env(monkeypatch):
    user = SimpleNamespace(id=5, telegram_id=1, balance_kopeks=0, full_name='x', username=None)
    calls = SimpleNamespace(subscription=None, grant=AsyncMock(), reserve=AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False, raising=False)
    monkeypatch.setattr(module, 'get_user_by_id', AsyncMock(return_value=user))
    monkeypatch.setattr(module, 'get_promocode_by_code', AsyncMock(return_value=_code()))
    monkeypatch.setattr(module, 'check_user_promocode_usage', AsyncMock(return_value=None))
    monkeypatch.setattr(module, 'create_promocode_use', calls.reserve)
    monkeypatch.setattr(module, 'get_subscription_by_user_id', AsyncMock(side_effect=lambda *_: calls.subscription))
    monkeypatch.setattr(promo_crud, 'count_user_recent_activations', AsyncMock(return_value=0))
    monkeypatch.setattr(wheel_crud, 'grant_free_spins', calls.grant)
    service = module.PromoCodeService.__new__(module.PromoCodeService)
    service.subscription_service = MagicMock()
    return service, calls


@pytest.mark.parametrize(
    'subscription',
    [
        None,
        _subscription(SubscriptionStatus.TRIAL.value, trial=True),
        _subscription(trial=True),
        _subscription(SubscriptionStatus.EXPIRED.value),
        _subscription(days=-1),
        _subscription(SubscriptionStatus.DISABLED.value),
    ],
    ids=['none', 'trial-status', 'active-trial', 'expired', 'end-date-passed', 'disabled'],
)
async def test_refused_without_spending_the_code(env, subscription):
    service, calls = env
    calls.subscription = subscription
    db = AsyncMock()

    result = await service.activate_promocode(db, 5, 'SPIN')

    assert result == {'success': False, 'error': 'paid_subscription_required'}
    calls.reserve.assert_not_awaited()
    calls.grant.assert_not_awaited()
    db.execute.assert_not_awaited()


async def test_paid_subscription_gets_one_spin(env):
    service, calls = env
    calls.subscription = _subscription()
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=1)

    result = await service.activate_promocode(db, 5, 'SPIN')

    assert result['success'] is True
    assert result['promocode']['type'] == PromoCodeType.WHEEL_SPIN.value
    assert 'спин' in result['description']
    calls.reserve.assert_awaited_once()
    calls.grant.assert_awaited_once()
    assert calls.grant.await_args.args[1:3] == (5, 1)


def test_refusal_text_is_not_the_generic_invalid_code():
    texts = SimpleNamespace(
        t=lambda _key, default: default, PROMOCODE_INVALID='invalid', PROMOCODE_EXPIRED='', PROMOCODE_USED='', ERROR=''
    )
    assert 'платной подпиской' in promocode_error_text(texts, 'paid_subscription_required')


def test_wheel_keyboard_only_for_spin_codes(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://web.example.ru/', raising=False)
    texts = SimpleNamespace(t=lambda _key, default: default)

    markup = wheel_spin_keyboard({'promocode': {'type': PromoCodeType.WHEEL_SPIN.value}}, texts)
    assert markup.inline_keyboard[0][0].web_app.url == 'https://web.example.ru/wheel'
    assert wheel_spin_keyboard({'promocode': {'type': PromoCodeType.BALANCE.value}}, texts) is None
