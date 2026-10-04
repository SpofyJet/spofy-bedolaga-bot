"""Spofy: finish purchases started on the subscription page (sub.spofyltd.ru).

The bot's global ``AUTO_PURCHASE_AFTER_TOPUP_ENABLED`` stays OFF. Only carts the
subscription-page bridge saved (``source == 'spofy_subpage'``) are completed after
a top-up — every other cart (bot, cabinet, mini app) keeps the bot's normal
behaviour. Called from ``app/services/payment/common.py`` right after the standard
auto-purchase.
"""

from __future__ import annotations

from typing import Any

import structlog
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.services.spofy_subpage_context import subpage_purchase_context
from app.services.user_cart_service import user_cart_service


logger = structlog.get_logger(__name__)

SUBPAGE_SOURCE = 'spofy_subpage'

# The payment may be credited a hair differently from what was requested (provider rounding,
# crypto rates); beyond this the purchase is NOT completed (the money stays on the balance).
FUNDING_TOLERANCE = 0.02
FUNDING_TOLERANCE_MIN_KOPEKS = 100


def is_subpage_cart(cart: dict[str, Any] | None) -> bool:
    return bool(cart) and cart.get('source') == SUBPAGE_SOURCE


async def tag_current_cart_as_subpage(user_id: int) -> bool:
    """Re-tag the cart the cabinet helpers just saved (devices / traffic carry source='cabinet')."""
    cart = await user_cart_service.get_user_cart(user_id)
    if not cart:
        return False
    cart['source'] = SUBPAGE_SOURCE
    cart['return_to_cart'] = True  # keeps the fresh top-up intent for this purchase
    return await user_cart_service.save_user_cart(user_id, cart)


async def bind_cart_to_payment(user_id: int, *, price_kopeks: int, requested_kopeks: int) -> bool:
    """Remember what the page asked the customer to pay for this cart.

    Completion later checks that the money that just arrived is THIS payment — so a purchase is
    paid with its own payment and never with the customer's earlier balance, and an abandoned
    page cart cannot be bought by an unrelated top-up.
    """
    cart = await user_cart_service.get_user_cart(user_id)
    if not is_subpage_cart(cart):
        return False
    cart['spofy_price_kopeks'] = int(price_kopeks)
    cart['spofy_requested_kopeks'] = int(requested_kopeks)
    cart['return_to_cart'] = True
    return await user_cart_service.save_user_cart(user_id, cart)


def is_funded_by_payment(cart: dict[str, Any], credited_kopeks: int | None) -> bool:
    """True only if the credited amount is this cart's own payment and covers its price."""
    price = cart.get('spofy_price_kopeks')
    requested = cart.get('spofy_requested_kopeks')
    if not isinstance(price, int) or not isinstance(requested, int) or not isinstance(credited_kopeks, int):
        return False
    tolerance = max(FUNDING_TOLERANCE_MIN_KOPEKS, int(requested * FUNDING_TOLERANCE))
    return credited_kopeks >= price and abs(credited_kopeks - requested) <= tolerance


async def complete_subpage_carts_after_topup(
    db: AsyncSession, user: User, *, bot: Bot | None = None, credited_kopeks: int | None = None
) -> bool:
    """Complete only subscription-page carts funded by the payment that just arrived.

    Returns True when a purchase went through. At most ONE cart is bought per payment, and only
    if the credited amount is that cart's own payment (see ``is_funded_by_payment``).
    """
    if settings.is_auto_purchase_after_topup_enabled():
        # The standard auto-purchase already handled every cart, ours included.
        return False
    if not user or not getattr(user, 'id', None):
        return False

    carts: list[dict[str, Any]] = []
    seen_subscriptions: set[Any] = set()
    for cart in await user_cart_service.get_all_subscription_carts(user.id):
        if is_subpage_cart(cart):
            carts.append(cart)
            seen_subscriptions.add(cart.get('subscription_id'))
    global_cart = await user_cart_service.get_user_cart(user.id)
    if is_subpage_cart(global_cart) and global_cart.get('subscription_id') not in seen_subscriptions:
        carts.append(global_cart)

    if not carts:
        return False

    if not await user_cart_service.has_topup_intent(user.id):
        logger.info('spofy subpage: cart found but no fresh top-up intent, skipping', user_id=user.id)
        return False

    funded = [cart for cart in carts if is_funded_by_payment(cart, credited_kopeks)]
    if not funded:
        logger.info(
            'spofy subpage: top-up is not the payment of any page cart, balance left untouched',
            user_id=user.id,
            credited=credited_kopeks,
            carts=len(carts),
        )
        return False

    # Lazy import: subscription_auto_purchase_service imports payment helpers.
    from app.services.subscription_auto_purchase_service import _process_single_cart

    completed = False
    for cart in funded:
        try:
            # Пометка для админ-уведомлений: покупка со страницы подписки.
            with subpage_purchase_context():
                processed = await _process_single_cart(db, user, cart, bot=bot)
            if processed:
                completed = True
                break  # one payment buys one cart: never reach into the balance for a second
        except Exception as error:  # one cart must not block the others
            logger.error('spofy subpage: cart completion failed', user_id=user.id, error=error, exc_info=True)

    if completed:
        await user_cart_service.clear_topup_intent(user.id)
        logger.info('spofy subpage: purchase completed after top-up', user_id=user.id, carts=len(carts))
    return completed
