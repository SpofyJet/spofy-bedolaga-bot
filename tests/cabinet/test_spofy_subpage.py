"""Spofy subscription-page bridge (``app/cabinet/routes/spofy_subpage.py``).

The bridge must:
* answer 404 when ``SPOFY_SUBPAGE_API_KEY`` is unset and 401 on a wrong key;
* never spend the user's balance — every checkout saves a cart and creates a
  top-up for the FULL price through the cabinet's own ``create_topup``;
* work with the bot's global ``AUTO_PURCHASE_AFTER_TOPUP_ENABLED`` OFF — its carts are
  tagged ``source='spofy_subpage'`` and only those are completed after a top-up
  (``app/services/spofy_subpage_service.py``).

Handlers are called directly (house pattern); the HTTP layer is exercised with
a minimal FastAPI app for the key check only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.cabinet.routes import spofy_subpage as bridge
from app.config import settings


KEY = 'k' * 40


def _tariff(**over):
    base = dict(
        id=7,
        name='Base',
        description=None,
        is_active=True,
        is_daily=False,
        period_prices={'30': 19900, '90': 49900},
        traffic_limit_gb=0,
        device_limit=3,
        allowed_squads=['sq'],
        highlight_period_days=90,
    )
    base.update(over)
    tariff = SimpleNamespace(**base)
    tariff.has_configured_price_for_period = lambda days: str(days) in tariff.period_prices
    tariff.is_available_for_promo_group = lambda _pg: True
    return tariff


def _subscription(**over):
    tariff = over.pop('tariff', _tariff())
    base = dict(
        id=42,
        status='active',
        actual_status='active',
        is_trial=False,
        tariff_id=tariff.id if tariff else None,
        tariff=tariff,
        end_date=datetime.now(UTC) + timedelta(days=10),
        device_limit=3,
        traffic_limit_gb=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _user(**over):
    base = dict(id=5, status='active', balance_kopeks=0, restriction_subscription=False, restriction_topup=False)
    base.update(over)
    user = SimpleNamespace(**base)
    user.get_primary_promo_group = lambda: None
    return user


def _method(**over):
    from app.cabinet.schemas.balance import PaymentMethodResponse

    base = dict(id='yookassa', name='Card', description=None, min_amount_kopeks=10000, max_amount_kopeks=10**8)
    base.update(over)
    return PaymentMethodResponse(**base)


def _pricing(final, original=None):
    return SimpleNamespace(
        final_total=final,
        original_total=original if original is not None else final,
        promo_offer_discount=0,
        breakdown={},
    )


@pytest.fixture
def auto_on(monkeypatch):
    # name kept for the fixtures below: the global switch is deliberately OFF
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    monkeypatch.setattr(bridge, 'tag_current_cart_as_subpage', AsyncMock(return_value=True))


@pytest.fixture
def owner(monkeypatch):
    user, sub = _user(), _subscription()
    monkeypatch.setattr(bridge, 'resolve_owner', AsyncMock(return_value=(user, sub)))
    return user, sub


@pytest.fixture
def topup(monkeypatch):
    mock = AsyncMock(
        return_value=SimpleNamespace(payment_url='https://pay.example/x', payment_id='17', qr_payload=None, expires_at=None)
    )
    monkeypatch.setattr(bridge, 'create_topup', mock)
    monkeypatch.setattr(bridge, 'get_payment_methods', AsyncMock(return_value=[_method()]))
    return mock


# ───────────── auth ─────────────


def _client():
    app = FastAPI()
    app.include_router(bridge.router)

    async def _db():
        yield None

    app.dependency_overrides[bridge.get_cabinet_db] = _db
    return TestClient(app)


def test_router_hidden_without_key(monkeypatch):
    monkeypatch.delenv(bridge.KEY_ENV, raising=False)
    assert _client().get('/spofy-subpage/abcdefgh/offer').status_code == 404


def test_short_key_counts_as_unset(monkeypatch):
    monkeypatch.setenv(bridge.KEY_ENV, 'short')
    assert _client().get('/spofy-subpage/abcdefgh/offer', headers={'X-Spofy-Subpage-Key': 'short'}).status_code == 404


def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setenv(bridge.KEY_ENV, KEY)
    response = _client().get('/spofy-subpage/abcdefgh/offer', headers={'X-Spofy-Subpage-Key': 'x' * 40})
    assert response.status_code == 401


async def test_right_key_passes(monkeypatch):
    monkeypatch.setenv(bridge.KEY_ENV, KEY)
    assert await bridge.require_subpage_key(KEY) is None


@pytest.mark.parametrize('bad', ['', 'a', 'has space', 'x' * 65, '../etc'])
async def test_resolve_rejects_malformed_short_uuid(bad):
    with pytest.raises(HTTPException) as error:
        await bridge.resolve_owner(None, bad)
    assert error.value.status_code == 404


# ───────────── checkout ─────────────


async def test_checkout_works_with_global_auto_purchase_off(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=19900))
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')
    result = await bridge.checkout('abcdefgh', body, db=None)
    assert result['payment_url'] == 'https://pay.example/x'
    topup.assert_awaited_once()


async def test_renew_checkout_tops_up_full_price_and_never_charges(monkeypatch, auto_on, owner, topup):
    user, sub = owner
    user.balance_kopeks = 10**9  # rich user: the cabinet would charge — the bridge must not
    save = AsyncMock(return_value=49900)
    monkeypatch.setattr(bridge, 'save_renewal_cart', save)

    from app.services import subscription_renewal_service

    monkeypatch.setattr(
        subscription_renewal_service.SubscriptionRenewalService,
        'finalize',
        AsyncMock(side_effect=AssertionError('balance must never be charged')),
    )

    body = bridge.CheckoutRequest(kind='renew', period_days=90, payment_method='yookassa')
    result = await bridge.checkout('abcdefgh', body, db=None)

    save.assert_awaited_once_with(None, user, sub, 90)
    request = topup.await_args.kwargs['request']
    assert request.amount_kopeks == 49900
    assert request.payment_method == 'yookassa'
    assert result['payment_url'] == 'https://pay.example/x'
    assert result['price_kopeks'] == 49900
    assert result['before']['device_limit'] == 3


async def test_amount_raised_to_method_minimum(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=5000))
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')
    result = await bridge.checkout('abcdefgh', body, db=None)
    assert topup.await_args.kwargs['request'].amount_kopeks == 10000
    assert result['amount_kopeks'] == 10000 and result['price_kopeks'] == 5000


async def test_unknown_method_rejected(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=19900))
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='nope')
    with pytest.raises(HTTPException) as error:
        await bridge.checkout('abcdefgh', body, db=None)
    assert error.value.status_code == 400
    topup.assert_not_awaited()


async def test_restricted_user_cannot_checkout(monkeypatch, auto_on, topup):
    user, sub = _user(restriction_topup=True), _subscription()
    monkeypatch.setattr(bridge, 'resolve_owner', AsyncMock(return_value=(user, sub)))
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')
    with pytest.raises(HTTPException) as error:
        await bridge.checkout('abcdefgh', body, db=None)
    assert error.value.status_code == 403


async def test_devices_checkout_saves_cabinet_cart(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(
        bridge, 'get_device_price', AsyncMock(return_value={'available': True, 'total_price_kopeks': 15000})
    )
    save = AsyncMock(return_value={'success': True})
    monkeypatch.setattr(bridge, 'save_devices_cart', save)
    body = bridge.CheckoutRequest(kind='devices', devices=2, payment_method='yookassa')
    await bridge.checkout('abcdefgh', body, db=None)
    assert save.await_args.kwargs['request'].devices == 2
    assert save.await_args.kwargs['subscription_id'] == 42
    bridge.tag_current_cart_as_subpage.assert_awaited_once_with(5)  # cabinet cart re-tagged
    assert topup.await_args.kwargs['request'].amount_kopeks == 15000


async def test_devices_unavailable(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(
        bridge, 'get_device_price', AsyncMock(return_value={'available': False, 'reason': 'max'})
    )
    body = bridge.CheckoutRequest(kind='devices', devices=1, payment_method='yookassa')
    with pytest.raises(HTTPException) as error:
        await bridge.checkout('abcdefgh', body, db=None)
    assert error.value.status_code == 400
    topup.assert_not_awaited()


async def test_traffic_package_must_exist(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(
        bridge, 'get_traffic_packages', AsyncMock(return_value=[SimpleNamespace(gb=50, price_kopeks=9900)])
    )
    save = AsyncMock()
    monkeypatch.setattr(bridge, 'save_traffic_cart', save)
    with pytest.raises(HTTPException):
        await bridge.checkout(
            'abcdefgh', bridge.CheckoutRequest(kind='traffic', traffic_gb=10, payment_method='yookassa'), db=None
        )
    await bridge.checkout(
        'abcdefgh', bridge.CheckoutRequest(kind='traffic', traffic_gb=50, payment_method='yookassa'), db=None
    )
    assert save.await_args.kwargs['request'].gb == 50
    assert topup.await_args.kwargs['request'].amount_kopeks == 10000  # 99 ₽ raised to the 100 ₽ minimum


# ───────────── carts ─────────────


async def test_renewal_cart_mirrors_cabinet_extend_cart(monkeypatch):
    user, sub = _user(), _subscription()
    monkeypatch.setattr(
        bridge.pricing_engine, 'calculate_renewal_price', AsyncMock(return_value=_pricing(49900, 59900))
    )
    monkeypatch.setattr(bridge, 'get_tariff_by_id', AsyncMock(return_value=sub.tariff))
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(bridge.user_cart_service, 'save_user_cart', save)

    price = await bridge.save_renewal_cart(None, user, sub, 90)

    assert price == 49900
    user_id, cart = save.await_args.args
    assert user_id == 5
    assert cart['cart_mode'] == 'extend'
    assert cart['source'] == 'spofy_subpage'
    assert cart['return_to_cart'] is True  # sets the fresh top-up intent
    assert cart['missing_amount'] == 49900
    assert cart['subscription_id'] == 42 and cart['period_days'] == 90
    assert cart['discount_percent'] == 16
    assert cart['allowed_squads'] == ['sq']


async def test_renewal_cart_rejects_trial_and_unknown_period(monkeypatch):
    with pytest.raises(HTTPException):
        await bridge.save_renewal_cart(None, _user(), _subscription(is_trial=True), 30)
    with pytest.raises(HTTPException):
        await bridge.save_renewal_cart(None, _user(), _subscription(), 45)


async def test_tariff_cart_for_trial_user(monkeypatch):
    user, sub = _user(), _subscription(is_trial=True, tariff=None, device_limit=1)
    tariff = _tariff()
    monkeypatch.setattr(settings, 'is_tariffs_mode', lambda: True)
    monkeypatch.setattr(settings, 'is_multi_tariff_enabled', lambda: False)
    monkeypatch.setattr(bridge, 'get_tariff_by_id', AsyncMock(return_value=tariff))
    monkeypatch.setattr(
        bridge.pricing_engine, 'calculate_tariff_purchase_price', AsyncMock(return_value=_pricing(19900))
    )
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(bridge.user_cart_service, 'save_user_cart', save)

    assert await bridge.save_tariff_cart(None, user, sub, 7, 30) == 19900
    cart = save.await_args.args[1]
    assert cart['cart_mode'] == 'tariff_purchase' and cart['tariff_id'] == 7
    assert cart['return_to_cart'] is True and cart['device_limit'] == 3


async def test_tariff_cart_refuses_daily_and_multi_tariff(monkeypatch):
    monkeypatch.setattr(settings, 'is_tariffs_mode', lambda: True)
    monkeypatch.setattr(settings, 'is_multi_tariff_enabled', lambda: True)
    with pytest.raises(HTTPException):
        await bridge.save_tariff_cart(None, _user(), _subscription(), 7, 30)
    monkeypatch.setattr(settings, 'is_multi_tariff_enabled', lambda: False)
    monkeypatch.setattr(bridge, 'get_tariff_by_id', AsyncMock(return_value=_tariff(is_daily=True)))
    with pytest.raises(HTTPException):
        await bridge.save_tariff_cart(None, _user(), _subscription(), 7, 30)


# ───────────── offer ─────────────


async def test_offer_for_trial_user_lists_tariffs_not_renewal(monkeypatch, auto_on):
    user, sub = _user(), _subscription(is_trial=True)
    monkeypatch.setattr(bridge, 'resolve_owner', AsyncMock(return_value=(user, sub)))
    monkeypatch.setattr(bridge, 'get_payment_methods', AsyncMock(return_value=[_method()]))
    renewal = AsyncMock(return_value=[])
    monkeypatch.setattr(bridge, 'get_renewal_options', renewal)
    monkeypatch.setattr(bridge, 'tariff_offers', AsyncMock(return_value=[{'id': 7}]))
    monkeypatch.setattr(bridge, 'get_device_price', AsyncMock(side_effect=HTTPException(400, 'legacy')))
    monkeypatch.setattr(bridge, 'get_traffic_packages', AsyncMock(return_value=[]))
    monkeypatch.setattr(bridge, 'get_trial_info', AsyncMock(return_value=None))

    offer = await bridge.get_offer('abcdefgh', db=None)

    renewal.assert_not_awaited()
    assert offer['tariffs'] == [{'id': 7}]
    assert offer['devices']['available'] is False  # one failing part does not break the offer
    assert offer['checkout_enabled'] is True
    assert offer['payment_methods'][0]['id'] == 'yookassa'


# ───────────── completion after top-up (app/services/spofy_subpage_service.py) ─────────────

from app.services import spofy_subpage_service as completion  # noqa: E402


def _carts(monkeypatch, *, per_sub, global_cart, intent=True):
    svc = completion.user_cart_service
    monkeypatch.setattr(svc, 'get_all_subscription_carts', AsyncMock(return_value=per_sub))
    monkeypatch.setattr(svc, 'get_user_cart', AsyncMock(return_value=global_cart))
    monkeypatch.setattr(svc, 'has_topup_intent', AsyncMock(return_value=intent))
    monkeypatch.setattr(svc, 'clear_topup_intent', AsyncMock(return_value=True))
    process = AsyncMock(return_value=True)
    from app.services import subscription_auto_purchase_service

    monkeypatch.setattr(subscription_auto_purchase_service, '_process_single_cart', process)
    return process


async def test_completion_only_processes_subpage_carts(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    ours = {'source': 'spofy_subpage', 'cart_mode': 'extend', 'subscription_id': 1}
    cabinet = {'source': 'cabinet', 'cart_mode': 'extend', 'subscription_id': 2}
    process = _carts(monkeypatch, per_sub=[ours, cabinet], global_cart=cabinet)

    assert await completion.complete_subpage_carts_after_topup(None, _user()) is True
    assert [c.args[2] for c in process.await_args_list] == [ours]
    completion.user_cart_service.clear_topup_intent.assert_awaited_once_with(5)


async def test_completion_skips_when_global_switch_on(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True, raising=False)
    process = _carts(monkeypatch, per_sub=[{'source': 'spofy_subpage', 'cart_mode': 'extend'}], global_cart=None)
    assert await completion.complete_subpage_carts_after_topup(None, _user()) is False
    process.assert_not_awaited()  # the standard auto-purchase already ran


async def test_completion_needs_fresh_intent(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(
        monkeypatch, per_sub=[], global_cart={'source': 'spofy_subpage', 'cart_mode': 'add_traffic'}, intent=False
    )
    assert await completion.complete_subpage_carts_after_topup(None, _user()) is False
    process.assert_not_awaited()


async def test_completion_ignores_plain_topups(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(monkeypatch, per_sub=[], global_cart={'source': 'cabinet', 'cart_mode': 'extend'})
    assert await completion.complete_subpage_carts_after_topup(None, _user()) is False
    process.assert_not_awaited()


async def test_tagging_rewrites_source_and_intent(monkeypatch):
    svc = completion.user_cart_service
    monkeypatch.setattr(svc, 'get_user_cart', AsyncMock(return_value={'cart_mode': 'add_devices', 'source': 'cabinet'}))
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(svc, 'save_user_cart', save)
    assert await completion.tag_current_cart_as_subpage(5) is True
    saved = save.await_args.args[1]
    assert saved['source'] == 'spofy_subpage' and saved['return_to_cart'] is True
