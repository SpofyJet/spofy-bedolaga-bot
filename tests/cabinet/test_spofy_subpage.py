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

import asyncio
import contextlib
import fnmatch
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.cabinet.routes import spofy_subpage as bridge
from app.config import Settings, settings
from app.services.user_cart_service import UserCartService


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
        return_value=SimpleNamespace(
            payment_url='https://pay.example/x', payment_id='17', qr_payload=None, expires_at=None
        )
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
    monkeypatch.setattr(bridge, 'get_device_price', AsyncMock(return_value={'available': False, 'reason': 'max'}))
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


async def test_concurrent_same_checkout_replays_one_payment(monkeypatch, auto_on, owner, topup):
    # Two tabs buying the same thing at the same time must share ONE payment: the second
    # checkout waits for the first and replays its payment instead of overwriting the single
    # cart slot (the overwrite used to unmatch the first payment — money hung on the balance).
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=19900))
    bound: list[str] = []

    async def slow_bind(user_id: int, **kwargs: object) -> bool:
        bound.append('bind')
        await asyncio.sleep(0.05)
        return True

    monkeypatch.setattr(bridge, 'bind_cart_to_payment', slow_bind)
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')

    first, second = await asyncio.gather(
        bridge.checkout('abcdefgh', body, db=None),
        bridge.checkout('abcdefgh', body, db=None),
    )

    assert bound == ['bind']  # cart bound exactly once: no interleaved second checkout
    assert topup.await_count == 1  # ...and exactly one payment created
    assert second == first  # the second tab got the same payment, not a new one
    assert second['payment_id'] == '17'


async def test_concurrent_different_checkout_gets_409(monkeypatch, auto_on, owner, topup):
    # A DIFFERENT cart while a checkout is in flight must not wait and overwrite the slot —
    # it fails fast with 409 and can be retried once the first payment is created.
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=19900))

    async def slow_topup(**kwargs: object) -> object:
        await asyncio.sleep(0.05)
        return SimpleNamespace(
            payment_url='https://pay.example/x', payment_id='17', qr_payload=None, expires_at=None
        )

    monkeypatch.setattr(bridge, 'create_topup', slow_topup)
    first = asyncio.create_task(
        bridge.checkout(
            'abcdefgh', bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa'), db=None
        )
    )
    await asyncio.sleep(0)  # let the first checkout claim the slot
    with pytest.raises(HTTPException) as error:
        await bridge.checkout(
            'abcdefgh', bridge.CheckoutRequest(kind='renew', period_days=90, payment_method='yookassa'), db=None
        )
    assert error.value.status_code == 409
    assert (await first)['payment_id'] == '17'


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
    monkeypatch.setattr(Settings, 'is_tariffs_mode', lambda self: True)
    monkeypatch.setattr(Settings, 'is_multi_tariff_enabled', lambda self: False)
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
    monkeypatch.setattr(Settings, 'is_tariffs_mode', lambda self: True)
    monkeypatch.setattr(Settings, 'is_multi_tariff_enabled', lambda self: True)
    with pytest.raises(HTTPException):
        await bridge.save_tariff_cart(None, _user(), _subscription(), 7, 30)
    monkeypatch.setattr(Settings, 'is_multi_tariff_enabled', lambda self: False)
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


async def test_device_offer_quotes_each_count_from_the_bot(monkeypatch):
    # 1st device is free (inside the tariff limit), the rest are prorated by the bot
    def price(devices, **_):
        total = max(0, devices - 1) * 96_700
        return {'available': True, 'total_price_kopeks': total, 'can_add': 3, 'base_device_price_kopeks': 100_000}

    monkeypatch.setattr(bridge, 'get_device_price', AsyncMock(side_effect=price))
    offer = await bridge.device_offer(None, _user(), _subscription())

    assert [q['total_price_kopeks'] for q in offer['quotes']] == [0, 96_700, 193_400]
    assert offer['base_device_price_kopeks'] == 100_000


async def test_device_offer_stops_at_first_unavailable_count(monkeypatch):
    def price(devices, **_):
        if devices > 2:
            return {'available': False, 'reason': 'max'}
        return {'available': True, 'total_price_kopeks': devices * 1000, 'can_add': None}

    monkeypatch.setattr(bridge, 'get_device_price', AsyncMock(side_effect=price))
    offer = await bridge.device_offer(None, _user(), _subscription())

    assert [q['devices'] for q in offer['quotes']] == [1, 2]


async def test_offer_survives_unexpected_errors_in_parts(monkeypatch, auto_on):
    # multi-tariff edge case: a cabinet helper raises a plain exception, not HTTPException
    user, sub = _user(), _subscription()
    monkeypatch.setattr(bridge, 'resolve_owner', AsyncMock(return_value=(user, sub)))
    monkeypatch.setattr(bridge, 'get_payment_methods', AsyncMock(return_value=[_method()]))
    monkeypatch.setattr(bridge, 'get_renewal_options', AsyncMock(return_value=[]))
    monkeypatch.setattr(bridge, 'tariff_offers', AsyncMock(side_effect=AttributeError('tariff')))
    monkeypatch.setattr(bridge, 'get_device_price', AsyncMock(side_effect=RuntimeError('boom')))
    monkeypatch.setattr(bridge, 'get_traffic_packages', AsyncMock(side_effect=KeyError('x')))
    monkeypatch.setattr(bridge, 'get_trial_info', AsyncMock(side_effect=ValueError('y')))

    offer = await bridge.get_offer('abcdefgh', db=None)

    assert offer['devices']['available'] is False
    assert offer['traffic'] == [] and offer['tariffs'] == [] and offer['trial'] is None
    assert offer['checkout_enabled'] is True


async def test_unexpected_checkout_error_is_a_502_with_its_type(monkeypatch, auto_on, owner):
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(side_effect=AttributeError('lazy load')))
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')
    with pytest.raises(HTTPException) as caught:
        await bridge.checkout('abcdefgh', body, db=None)
    assert caught.value.status_code == 502
    assert 'AttributeError' in caught.value.detail


# ───────────── completion after top-up (app/services/spofy_subpage_service.py) ─────────────

from app.services import spofy_subpage_service as completion


@pytest.fixture(autouse=True)
def fresh_checkout_serializer(monkeypatch):
    # Successful checkouts are remembered for replay; every test gets an empty serializer
    # so one test's remembered payment cannot be replayed into the next one.
    monkeypatch.setattr(bridge, 'checkout_serializer', completion.CheckoutSerializer())


BOUND = {'source': 'spofy_subpage', 'spofy_price_kopeks': 49900, 'spofy_requested_kopeks': 49900}


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
    ours = {**BOUND, 'cart_mode': 'extend', 'subscription_id': 1}
    cabinet = {'source': 'cabinet', 'cart_mode': 'extend', 'subscription_id': 2}
    process = _carts(monkeypatch, per_sub=[ours, cabinet], global_cart=cabinet)

    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is True
    assert [c.args[2] for c in process.await_args_list] == [ours]
    completion.user_cart_service.clear_topup_intent.assert_awaited_once_with(5)


async def test_completion_skips_when_global_switch_on(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True, raising=False)
    process = _carts(monkeypatch, per_sub=[{**BOUND, 'cart_mode': 'extend'}], global_cart=None)
    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is False
    process.assert_not_awaited()  # the standard auto-purchase already ran


async def test_completion_needs_fresh_intent(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(
        monkeypatch, per_sub=[], global_cart={**BOUND, 'cart_mode': 'add_traffic'}, intent=False
    )
    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is False
    process.assert_not_awaited()


async def test_completion_ignores_plain_topups(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(monkeypatch, per_sub=[], global_cart={'source': 'cabinet', 'cart_mode': 'extend'})
    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is False
    process.assert_not_awaited()


async def test_tagging_rewrites_source_and_intent(monkeypatch):
    svc = completion.user_cart_service
    monkeypatch.setattr(svc, 'get_user_cart', AsyncMock(return_value={'cart_mode': 'add_devices', 'source': 'cabinet'}))
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(svc, 'save_user_cart', save)
    assert await completion.tag_current_cart_as_subpage(5) is True
    saved = save.await_args.args[1]
    assert saved['source'] == 'spofy_subpage' and saved['return_to_cart'] is True


# ───────────── the purchase is paid by its own payment, never from the balance ─────────────


async def _complete(monkeypatch, carts, credited):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(monkeypatch, per_sub=carts, global_cart=None)
    result = await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=credited)
    return result, process


async def test_unbound_cart_is_never_completed(monkeypatch):
    result, process = await _complete(monkeypatch, [{'source': 'spofy_subpage', 'cart_mode': 'extend'}], 49900)
    assert result is False
    process.assert_not_awaited()


async def test_unrelated_topup_does_not_buy_an_abandoned_cart(monkeypatch):
    # the customer abandoned a 499 ₽ renewal and tops up 1 000 ₽ in the bot
    result, process = await _complete(monkeypatch, [{**BOUND, 'cart_mode': 'extend'}], 100_000)
    assert result is False
    process.assert_not_awaited()


async def test_payment_smaller_than_price_never_reaches_into_balance(monkeypatch):
    result, process = await _complete(monkeypatch, [{**BOUND, 'cart_mode': 'extend'}], 40_000)
    assert result is False
    process.assert_not_awaited()


async def test_small_provider_rounding_is_tolerated(monkeypatch):
    result, process = await _complete(monkeypatch, [{**BOUND, 'cart_mode': 'extend'}], 49900 + 150)
    assert result is True
    process.assert_awaited_once()


async def test_two_identical_carts_one_payment_buys_only_one(monkeypatch):
    a = {**BOUND, 'cart_mode': 'extend', 'subscription_id': 1}
    b = {**BOUND, 'cart_mode': 'extend', 'subscription_id': 2}
    result, process = await _complete(monkeypatch, [a, b], 49900)
    assert result is True
    assert process.await_count == 1


async def test_checkout_binds_the_cart_to_its_payment(monkeypatch, auto_on, owner, topup):
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=5000))
    bind = AsyncMock(return_value=True)
    monkeypatch.setattr(bridge, 'bind_cart_to_payment', bind)
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')
    await bridge.checkout('abcdefgh', body, db=None)
    kwargs = bind.await_args.kwargs
    assert kwargs['price_kopeks'] == 5000
    assert kwargs['requested_kopeks'] == topup.await_args.kwargs['request'].amount_kopeks


async def test_binding_marks_price_and_requested_amount(monkeypatch):
    svc = completion.user_cart_service
    monkeypatch.setattr(svc, 'get_user_cart', AsyncMock(return_value={'source': 'spofy_subpage'}))
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(svc, 'save_user_cart', save)
    assert await completion.bind_cart_to_payment(5, price_kopeks=4900, requested_kopeks=10000) is True
    saved = save.await_args.args[1]
    assert saved['spofy_price_kopeks'] == 4900 and saved['spofy_requested_kopeks'] == 10000


# ───────────── BUG 1: оплата по «долгой» ссылке — TTL корзины и намерения ─────────────


def test_cart_ttls_cover_payment_link_lifetime():
    """Метка намерения не должна умирать раньше корзины, а корзина — раньше реальной
    жизни платёжных ссылок (инвойсы YooKassa/CryptoBot/Heleket/XRocket живут сутки+)."""
    assert settings.CART_AUTOPURCHASE_INTENT_TTL_SECONDS >= settings.CART_TTL_SECONDS
    assert settings.CART_TTL_SECONDS >= 24 * 3600


class _ClockedRedis:
    """Минимальный фейк Redis с настоящими TTL: часы подаёт тест (прокрутка времени)."""

    def __init__(self, clock):
        self._clock = clock
        self._data: dict[str, tuple[float, str]] = {}

    def _live(self, key: str) -> bool:
        item = self._data.get(key)
        if item is None:
            return False
        if item[0] <= self._clock():
            del self._data[key]
            return False
        return True

    async def setex(self, key, ttl, value):
        self._data[key] = (self._clock() + int(ttl), value)
        return True

    async def get(self, key):
        if not self._live(key):
            return None
        return self._data[key][1]

    async def delete(self, key):
        existed = self._live(key)
        self._data.pop(key, None)
        return 1 if existed else 0

    async def exists(self, key):
        return 1 if self._live(key) else 0

    async def scan(self, cursor=0, match=None, count=50):
        keys = [key for key in list(self._data) if self._live(key)]
        if match:
            keys = [key for key in keys if fnmatch.fnmatch(key, match)]
        return 0, keys


@pytest.fixture
def clocked_carts(monkeypatch):
    """Настоящий UserCartService на фейковых часах — время в тесте крутим сами."""
    clock = [0.0]
    service = UserCartService()
    service._redis_client = _ClockedRedis(lambda: clock[0])
    service._initialized = True
    monkeypatch.setattr(completion, 'user_cart_service', service)
    return service, clock


def _stuck_process(monkeypatch):
    process = AsyncMock(return_value=True)
    from app.services import subscription_auto_purchase_service

    monkeypatch.setattr(subscription_auto_purchase_service, '_process_single_cart', process)
    return process


async def test_payment_two_hours_after_checkout_still_completes(monkeypatch, clocked_carts):
    """Оплата пришла через 2 часа после оформления. Старые TTL (корзина 1 ч,
    намерение 30 мин) уже убили бы и то и другое — деньги остались бы на балансе
    без покупки и без единого слова. С TTL 24 ч покупка завершается."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    service, clock = clocked_carts
    cart = {**BOUND, 'cart_mode': 'extend', 'subscription_id': 1, 'return_to_cart': True}
    await service.save_user_cart(5, cart)
    assert await service.has_topup_intent(5) is True
    clock[0] += 2 * 3600  # «прошло два часа» — юзер вернулся к ссылке и оплатил
    process = _stuck_process(monkeypatch)

    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is True
    process.assert_awaited_once()
    assert await service.has_topup_intent(5) is False  # намерение погашено успехом


async def test_old_short_ttls_reproduce_the_lost_purchase(monkeypatch, clocked_carts):
    """Контроль к предыдущему тесту: со старыми TTL (1 ч / 30 мин) та же оплата
    через 2 часа теряется — корзина и намерение мертвы, completion молчит."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    monkeypatch.setattr(settings, 'CART_TTL_SECONDS', 3600, raising=False)
    monkeypatch.setattr(settings, 'CART_AUTOPURCHASE_INTENT_TTL_SECONDS', 1800, raising=False)
    service, clock = clocked_carts
    cart = {**BOUND, 'cart_mode': 'extend', 'subscription_id': 1, 'return_to_cart': True}
    await service.save_user_cart(5, cart)
    clock[0] += 2 * 3600
    process = _stuck_process(monkeypatch)

    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is False
    process.assert_not_awaited()


# ───────────── BUG 2: покупка исполняется по цене оформления, а не пересчёта ─────────────


def test_pinned_price_preferred_over_recomputed():
    from app.services.subscription_auto_purchase_service import _resolve_pinned_price

    assert _resolve_pinned_price(4900, 5000, format_user_id='u5', cart_mode='extend') == 4900
    assert _resolve_pinned_price(None, 5000, format_user_id='u5', cart_mode='extend') == 5000
    assert _resolve_pinned_price(0, 5000, format_user_id='u5', cart_mode='extend') == 5000


async def test_completion_passes_the_checkout_bound_price(monkeypatch):
    """spofy_price_kopeks уходит в исполнителя: пересчёт (промо истекло, пропорция
    изменилась) не имеет права поднять списание выше зачисленного платежа."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    cart = {**BOUND, 'spofy_price_kopeks': 49000, 'spofy_requested_kopeks': 49900, 'cart_mode': 'extend'}
    process = _carts(monkeypatch, per_sub=[cart], global_cart=None)

    assert await completion.complete_subpage_carts_after_topup(None, _user(), credited_kopeks=49900) is True
    assert process.await_args.kwargs['bound_price_kopeks'] == 49000


# ───────────── BUG 3: деньги на балансе, а покупки нет — юзер должен узнать ─────────────


def _telegram_user():
    user = _user()
    user.telegram_id = 777000
    user.language = 'ru'
    return user


def _bot_mock():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _keyboard_callbacks(bot):
    return [
        button.callback_data
        for row in bot.send_message.await_args.kwargs['reply_markup'].inline_keyboard
        for button in row
    ]


async def test_orphan_topup_without_intent_offers_return_to_cart(monkeypatch):
    """Метка намерения протухла раньше корзины: покупку не исполняем, но деньги на
    балансе — шлём уведомление с кнопкой «Вернуться к оформлению»."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(monkeypatch, per_sub=[], global_cart={**BOUND, 'cart_mode': 'extend'}, intent=False)
    bot = _bot_mock()

    assert await completion.complete_subpage_carts_after_topup(
        None, _telegram_user(), bot=bot, credited_kopeks=49900
    ) is False

    process.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs['chat_id'] == 777000
    assert 'баланс' in kwargs['text']
    callbacks = _keyboard_callbacks(bot)
    assert callbacks[0] == 'return_to_saved_cart'
    assert callbacks[-1] == 'back_to_menu'


async def test_orphan_topup_without_any_cart_points_to_buy(monkeypatch):
    """Корзины нет вовсе (истекла/перезаписана): деньги на балансе, ведём к покупке."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(monkeypatch, per_sub=[], global_cart=None)
    bot = _bot_mock()

    assert await completion.complete_subpage_carts_after_topup(
        None, _telegram_user(), bot=bot, credited_kopeks=49900
    ) is False

    process.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    callbacks = _keyboard_callbacks(bot)
    assert callbacks[0] == 'menu_buy'
    assert callbacks[-1] == 'back_to_menu'


async def test_completed_purchase_does_not_duplicate_notification(monkeypatch):
    """Покупка состоялась — юзера уже уведомил исполнитель покупки, дубль не шлём."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    process = _carts(monkeypatch, per_sub=[{**BOUND, 'cart_mode': 'extend'}], global_cart=None)
    bot = _bot_mock()

    assert await completion.complete_subpage_carts_after_topup(
        None, _telegram_user(), bot=bot, credited_kopeks=49900
    ) is True

    process.assert_awaited_once()
    bot.send_message.assert_not_awaited()


async def test_orphan_notification_respects_the_notifications_switch(monkeypatch):
    """Глобальный выключатель уведомлений гасит и orphan-уведомление (зеркало
    механизма _send_payment_success_notification)."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False, raising=False)
    monkeypatch.setattr(settings, 'ENABLE_NOTIFICATIONS', False, raising=False)
    _carts(monkeypatch, per_sub=[], global_cart=None, intent=False)
    bot = _bot_mock()

    await completion.complete_subpage_carts_after_topup(None, _telegram_user(), bot=bot, credited_kopeks=49900)

    bot.send_message.assert_not_awaited()


# ───────────── BUG 4: зависший первый checkout не вешает второй запрос ─────────────


async def test_wait_branch_times_out_with_409_instead_of_hanging(monkeypatch, auto_on, owner, topup):
    """Первый checkout завис (платёжка не отвечает). Второй с тем же fingerprint раньше
    ждал event.wait() бесконечно — теперь получает тот же 409, что и ветка 'busy'."""
    monkeypatch.setattr(bridge, 'CHECKOUT_WAIT_TIMEOUT_S', 0.05)

    async def stuck_checkout(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(bridge, 'save_renewal_cart', stuck_checkout)
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='yookassa')

    first = asyncio.create_task(bridge.checkout('abcdefgh', body, db=None))
    await asyncio.sleep(0)  # первый занял слот
    with pytest.raises(HTTPException) as error:
        await bridge.checkout('abcdefgh', body, db=None)
    assert error.value.status_code == 409

    first.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await first
