"""Spofy subscription-page bridge (sub.spofyltd.ru).

Lets the subscription page sell renewals, extra devices, traffic and tariffs to the
user who owns a Remnawave short UUID, without a login and WITHOUT EVER SPENDING THE
USER'S BALANCE.

Every checkout does what the cabinet does on insufficient funds — saves a cart with
``return_to_cart=True`` — tags it ``source='spofy_subpage'`` and creates a balance
top-up for the FULL price via the chosen payment method. When the payment lands,
``app/services/spofy_subpage_service.complete_subpage_carts_after_topup`` completes
ONLY such carts, so the bot's global ``AUTO_PURCHASE_AFTER_TOPUP_ENABLED`` can stay
off for every other purchase path. Prices, payment methods and top-ups all come from
the cabinet's own functions, so promo groups, discounts and every payment provider
behave exactly as in the cabinet.

Server-to-server only: the caller must send ``X-Spofy-Subpage-Key`` equal to the
``SPOFY_SUBPAGE_API_KEY`` environment variable (≥ 32 chars). Without the variable the
whole router answers 404.

Endpoints (under ``/cabinet``):
    GET  /spofy-subpage/{short_uuid}/offer
    POST /spofy-subpage/{short_uuid}/checkout
    GET  /spofy-subpage/{short_uuid}/payments/{method}/{payment_id}?active=0|1
"""

from __future__ import annotations

import hmac
import os
import re
from datetime import datetime
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database.crud.tariff import get_tariff_by_id, get_tariffs_for_user
from app.database.models import Subscription, SubscriptionStatus, User, UserStatus
from app.services.pricing_engine import pricing_engine
from app.services.spofy_subpage_service import SUBPAGE_SOURCE, tag_current_cart_as_subpage
from app.services.user_cart_service import user_cart_service

from ..dependencies import get_cabinet_db
from ..schemas.balance import TopUpRequest
from ..schemas.subscription import DevicePurchaseRequest, TrafficPurchaseRequest
from .balance import check_payment_status, create_topup, get_payment_methods, get_pending_payment_details
from .subscription_modules.devices import get_device_price, save_devices_cart
from .subscription_modules.purchase import get_trial_info
from .subscription_modules.renewal import get_renewal_options
from .subscription_modules.traffic import get_traffic_packages, save_traffic_cart


logger = structlog.get_logger(__name__)

KEY_ENV = 'SPOFY_SUBPAGE_API_KEY'
MIN_KEY_LENGTH = 32
MIN_TOPUP_KOPEKS = 1000  # TopUpRequest: ge=1000
SHORT_UUID_RE = re.compile(r'^[A-Za-z0-9_-]{6,64}$')

_key_header = APIKeyHeader(name='X-Spofy-Subpage-Key', auto_error=False)


async def require_subpage_key(key: str | None = Security(_key_header)) -> None:
    expected = (os.environ.get(KEY_ENV) or '').strip()
    if len(expected) < MIN_KEY_LENGTH:
        # Feature off: do not reveal that the router exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not Found')
    if not key or not hmac.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid key')


router = APIRouter(
    prefix='/spofy-subpage',
    tags=['Spofy Subpage'],
    dependencies=[Depends(require_subpage_key)],
    include_in_schema=False,
)


# ───────────────────────── helpers ─────────────────────────


async def resolve_owner(db: AsyncSession, short_uuid: str) -> tuple[User, Subscription]:
    """Subscription (and its user) behind a Remnawave short UUID."""
    if not SHORT_UUID_RE.match(short_uuid or ''):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscription not found')

    result = await db.execute(
        select(Subscription)
        .options(selectinload(Subscription.user), selectinload(Subscription.tariff))
        .where(Subscription.remnawave_short_uuid == short_uuid)
        .order_by(Subscription.id.desc())
        .limit(1)
    )
    subscription = result.scalar_one_or_none()
    if not subscription or not subscription.user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscription not found')

    user = subscription.user
    if getattr(user, 'status', None) in {UserStatus.BLOCKED.value, UserStatus.DELETED.value}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Account unavailable')
    return user, subscription


def snapshot(subscription: Subscription) -> dict[str, Any]:
    """What the page compares before/after payment to show «готово»."""
    end_date = subscription.end_date
    return {
        'status': getattr(subscription, 'actual_status', subscription.status),
        'is_trial': bool(subscription.is_trial),
        'tariff_id': subscription.tariff_id,
        'tariff_name': subscription.tariff.name if subscription.tariff_id and subscription.tariff else None,
        'end_date': end_date.isoformat() if isinstance(end_date, datetime) else None,
        'device_limit': subscription.device_limit,
        'traffic_limit_gb': subscription.traffic_limit_gb,
    }


async def _soft(coro: Any, default: Any) -> Any:
    """One unavailable part (e.g. devices for a legacy subscription) must not break the offer."""
    try:
        return await coro
    except HTTPException as error:
        logger.debug('spofy subpage: offer part unavailable', status=error.status_code, detail=str(error.detail))
        return default


def _restricted(user: User) -> str | None:
    if getattr(user, 'restriction_subscription', False):
        return 'subscription_restricted'
    if getattr(user, 'restriction_topup', False):
        return 'topup_restricted'
    return None


async def tariff_offers(db: AsyncSession, user: User, subscription: Subscription) -> list[dict[str, Any]]:
    """Tariffs a trial (or tariff-less) user can buy; plain period tariffs only (v1)."""
    if not settings.is_tariffs_mode() or settings.is_multi_tariff_enabled():
        return []

    promo_group = user.get_primary_promo_group() if hasattr(user, 'get_primary_promo_group') else None
    tariffs = await get_tariffs_for_user(db, promo_group.id if promo_group else None)

    offers: list[dict[str, Any]] = []
    for tariff in tariffs:
        if getattr(tariff, 'is_daily', False) or not tariff.period_prices:
            continue
        device_limit = subscription.device_limit if subscription.tariff_id == tariff.id else None
        periods = []
        for period_days in sorted(int(p) for p in tariff.period_prices):
            price = await pricing_engine.calculate_tariff_purchase_price(
                tariff, period_days, device_limit=device_limit, custom_traffic_gb=None, user=user
            )
            if price.final_total <= 0 and not tariff.has_configured_price_for_period(period_days):
                continue
            periods.append(
                {
                    'period_days': period_days,
                    'price_kopeks': price.final_total,
                    'original_price_kopeks': price.original_total
                    if price.original_total > price.final_total
                    else None,
                    'is_highlighted': tariff.highlight_period_days == period_days,
                }
            )
        if periods:
            offers.append(
                {
                    'id': tariff.id,
                    'name': tariff.name,
                    'description': tariff.description,
                    'traffic_limit_gb': tariff.traffic_limit_gb,
                    'device_limit': tariff.device_limit,
                    'periods': periods,
                }
            )
    return offers


async def save_renewal_cart(db: AsyncSession, user: User, subscription: Subscription, period_days: int) -> int:
    """Mirror of POST /subscription/renew on insufficient funds — without ever charging."""
    if subscription.is_trial:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Trial subscriptions are converted by buying a tariff')
    if settings.is_tariffs_mode() and not subscription.tariff_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Classic subscriptions cannot be renewed')
    actual_status = getattr(subscription, 'actual_status', subscription.status)
    if actual_status in {SubscriptionStatus.DISABLED.value, SubscriptionStatus.PENDING.value}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f'Cannot renew subscription with status: {actual_status}')

    tariff = subscription.tariff if subscription.tariff_id else None
    if tariff and tariff.is_active and tariff.period_prices:
        available_periods = [int(p) for p in tariff.period_prices]
    else:
        available_periods = settings.get_available_renewal_periods()
    if period_days not in available_periods:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Selected renewal period is not available')

    pricing = await pricing_engine.calculate_renewal_price(db, subscription, period_days, user=user)
    price = pricing.final_total
    original = pricing.original_total
    discount_percent = int((original - price) * 100 / original) if original > 0 and original != price else 0

    cart: dict[str, Any] = {
        'cart_mode': 'extend',
        'subscription_id': subscription.id,
        'tariff_id': subscription.tariff_id,
        'period_days': period_days,
        'total_price': price,
        'user_id': user.id,
        'saved_cart': True,
        'missing_amount': price,
        'return_to_cart': True,
        'description': f'Продление подписки на {period_days} дней' + (f' ({tariff.name})' if tariff else ''),
        'discount_percent': discount_percent,
        'consume_promo_offer': pricing.promo_offer_discount > 0,
        'source': SUBPAGE_SOURCE,
        'device_limit': subscription.device_limit,
    }
    if subscription.tariff_id:
        fresh_tariff = await get_tariff_by_id(db, subscription.tariff_id)
        cart['traffic_limit_gb'] = fresh_tariff.traffic_limit_gb if fresh_tariff else subscription.traffic_limit_gb
        cart['allowed_squads'] = (fresh_tariff.allowed_squads or []) if fresh_tariff else []
    else:
        cart['traffic_limit_gb'] = subscription.traffic_limit_gb

    await user_cart_service.save_user_cart(user.id, cart)
    return price


async def save_tariff_cart(
    db: AsyncSession, user: User, subscription: Subscription, tariff_id: int, period_days: int
) -> int:
    """Mirror of POST /subscription/purchase-tariff on insufficient funds (plain period tariffs)."""
    if not settings.is_tariffs_mode():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Tariffs mode is not enabled')
    if settings.is_multi_tariff_enabled():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Use the cabinet for multi-tariff purchases')

    tariff = await get_tariff_by_id(db, tariff_id)
    if not tariff or not tariff.is_active or getattr(tariff, 'is_daily', False):
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Tariff not found or inactive')
    promo_group = user.get_primary_promo_group() if hasattr(user, 'get_primary_promo_group') else None
    if not tariff.is_available_for_promo_group(promo_group.id if promo_group else None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, 'This tariff is not available for your promo group')
    if period_days not in [int(p) for p in (tariff.period_prices or {})]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Selected period is not available for this tariff')

    same_tariff = subscription.tariff_id == tariff.id
    device_limit = subscription.device_limit if same_tariff else None
    effective_device_limit = tariff.device_limit
    if same_tariff and (subscription.device_limit or 0) > (tariff.device_limit or 0):
        effective_device_limit = subscription.device_limit

    pricing = await pricing_engine.calculate_tariff_purchase_price(
        tariff, period_days, device_limit=device_limit, custom_traffic_gb=None, user=user
    )
    price = pricing.final_total
    if price <= 0 and not tariff.has_configured_price_for_period(period_days):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Invalid tariff period or pricing configuration')

    group_pcts = pricing.breakdown.get('group_discount_pct', {})
    cart = {
        'cart_mode': 'tariff_purchase',
        'tariff_id': tariff.id,
        'period_days': period_days,
        'total_price': price,
        'user_id': user.id,
        'saved_cart': True,
        'missing_amount': price,
        'return_to_cart': True,
        'description': f'Покупка тарифа {tariff.name} на {period_days} дней',
        'traffic_limit_gb': tariff.traffic_limit_gb,
        'device_limit': effective_device_limit,
        'allowed_squads': tariff.allowed_squads or [],
        'discount_percent': group_pcts.get('period', 0),
        'consume_promo_offer': pricing.promo_offer_discount > 0,
        'source': SUBPAGE_SOURCE,
        'subscription_id': subscription.id,
    }
    await user_cart_service.save_user_cart(user.id, cart)
    return price


# ───────────────────────── endpoints ─────────────────────────


@router.get('/{short_uuid}/offer')
async def get_offer(short_uuid: str, db: AsyncSession = Depends(get_cabinet_db)) -> dict[str, Any]:
    user, subscription = await resolve_owner(db, short_uuid)
    restriction = _restricted(user)

    methods = await _soft(get_payment_methods(user=user, db=db), [])
    renewal = (
        []
        if subscription.is_trial
        else await _soft(get_renewal_options(user=user, db=db, subscription_id=subscription.id), [])
    )
    tariffs = await tariff_offers(db, user, subscription) if (subscription.is_trial or not renewal) else []
    devices = await _soft(
        get_device_price(devices=1, subscription_id=subscription.id, user=user, db=db),
        {'available': False, 'reason_code': 'unavailable'},
    )
    traffic = await _soft(get_traffic_packages(user=user, db=db, subscription_id=subscription.id), [])
    trial = await _soft(get_trial_info(user=user, db=db), None)

    return {
        'checkout_enabled': restriction is None and bool(methods),
        'disabled_reason': restriction,
        'restriction': restriction,
        'subscription': snapshot(subscription),
        'renewal': [option.model_dump() for option in renewal],
        'tariffs': tariffs,
        'devices': devices,
        'traffic': [package.model_dump() for package in traffic],
        'trial': trial.model_dump() if trial else None,
        'payment_methods': [
            method.model_dump(
                include={'id', 'name', 'description', 'min_amount_kopeks', 'max_amount_kopeks', 'options'}
            )
            for method in methods
        ],
        'min_topup_kopeks': MIN_TOPUP_KOPEKS,
    }


class CheckoutRequest(BaseModel):
    kind: Literal['renew', 'devices', 'traffic', 'tariff']
    period_days: int | None = Field(None, ge=1, le=3650)
    devices: int | None = Field(None, ge=1, le=100)
    traffic_gb: int | None = Field(None, ge=0, le=100_000)
    tariff_id: int | None = Field(None, ge=1)
    payment_method: str = Field(..., min_length=1, max_length=64)
    payment_option: str | None = Field(None, max_length=64)


@router.post('/{short_uuid}/checkout')
async def checkout(
    short_uuid: str, body: CheckoutRequest, db: AsyncSession = Depends(get_cabinet_db)
) -> dict[str, Any]:
    user, subscription = await resolve_owner(db, short_uuid)
    restriction = _restricted(user)
    if restriction:
        raise HTTPException(status.HTTP_403_FORBIDDEN, restriction)
    before = snapshot(subscription)

    # 1. price + cart (never touches the balance)
    if body.kind == 'renew':
        if not body.period_days:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'period_days is required')
        price = await save_renewal_cart(db, user, subscription, body.period_days)
    elif body.kind == 'tariff':
        if not body.tariff_id or not body.period_days:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'tariff_id and period_days are required')
        price = await save_tariff_cart(db, user, subscription, body.tariff_id, body.period_days)
    elif body.kind == 'devices':
        if not body.devices:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'devices is required')
        info = await get_device_price(devices=body.devices, subscription_id=subscription.id, user=user, db=db)
        if not info.get('available'):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, info.get('reason') or 'Devices unavailable')
        price = int(info['total_price_kopeks'])
        await save_devices_cart(
            request=DevicePurchaseRequest(devices=body.devices), subscription_id=subscription.id, user=user, db=db
        )
        await tag_current_cart_as_subpage(user.id)
    else:
        if body.traffic_gb is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, 'traffic_gb is required')
        packages = await get_traffic_packages(user=user, db=db, subscription_id=subscription.id)
        package = next((p for p in packages if p.gb == body.traffic_gb), None)
        if not package:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Traffic package not available')
        price = int(package.price_kopeks)
        await save_traffic_cart(
            request=TrafficPurchaseRequest(gb=body.traffic_gb), user=user, db=db, subscription_id=subscription.id
        )
        await tag_current_cart_as_subpage(user.id)

    if price <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Nothing to pay — use the bot for free options')

    # 2. top-up for the full price via the chosen method (cabinet's own implementation)
    methods = await get_payment_methods(user=user, db=db)
    method = next((m for m in methods if m.id == body.payment_method), None)
    if not method:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Invalid or unavailable payment method')
    amount = max(price, method.min_amount_kopeks, MIN_TOPUP_KOPEKS)
    if amount > method.max_amount_kopeks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Amount exceeds the payment method limit')

    topup = await create_topup(
        request=TopUpRequest(
            amount_kopeks=amount, payment_method=method.id, payment_option=body.payment_option
        ),
        user=user,
        db=db,
    )
    logger.info(
        'spofy subpage checkout',
        user_id=user.id,
        subscription_id=subscription.id,
        kind=body.kind,
        price=price,
        amount=amount,
        method=method.id,
    )
    return {
        'payment_url': topup.payment_url,
        'payment_id': topup.payment_id,
        'method': method.id,
        'price_kopeks': price,
        'amount_kopeks': amount,
        'qr_payload': topup.qr_payload,
        'expires_at': topup.expires_at.isoformat() if topup.expires_at else None,
        'before': before,
    }


@router.get('/{short_uuid}/payments/{method}/{payment_id}')
async def payment_status(
    short_uuid: str,
    method: str,
    payment_id: str,
    active: bool = Query(False, description='Ask the provider (rate-limit on the caller side)'),
    db: AsyncSession = Depends(get_cabinet_db),
) -> dict[str, Any]:
    user, subscription = await resolve_owner(db, short_uuid)

    is_paid: bool | None = None
    status_text: str | None = None
    if payment_id.isdigit():
        try:
            if active:
                checked = await check_payment_status(method=method, payment_id=int(payment_id), user=user, db=db)
                if checked.payment:
                    is_paid, status_text = checked.payment.is_paid, checked.payment.status_text
            else:
                details = await get_pending_payment_details(method=method, payment_id=int(payment_id), user=user, db=db)
                is_paid, status_text = details.is_paid, details.status_text
        except HTTPException as error:
            logger.debug('spofy subpage: payment status unavailable', status=error.status_code)

    # Fresh read: the payment webhook / auto-purchase may have changed the subscription meanwhile.
    db.expire_all()
    _, subscription = await resolve_owner(db, short_uuid)
    return {'is_paid': is_paid, 'status_text': status_text, 'subscription': snapshot(subscription)}
