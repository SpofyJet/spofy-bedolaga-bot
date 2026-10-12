"""Spofy: finish purchases started on the subscription page (sub.spofyltd.ru).

The bot's global ``AUTO_PURCHASE_AFTER_TOPUP_ENABLED`` stays OFF. Only carts the
subscription-page bridge saved (``source == 'spofy_subpage'``) are completed after
a top-up — every other cart (bot, cabinet, mini app) keeps the bot's normal
behaviour. Called from ``app/services/payment/common.py`` right after the standard
auto-purchase.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
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

# A checkout replay window: while the payment link is still plausibly pending (the page itself
# keeps a pending payment for 30 minutes), an identical checkout request returns the same
# payment instead of creating a second one.
CHECKOUT_REPLAY_TTL_S = 30 * 60
_SLOTS_MAX = 5_000
_RECENT_MAX = 5_000


def checkout_fingerprint(short_uuid: str, payload: dict[str, Any]) -> str:
    """Idempotency key of one checkout attempt: same subscription + same cart + same method."""
    raw = json.dumps({'short_uuid': short_uuid, 'payload': payload}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


class _CheckoutSlot:
    __slots__ = ('done', 'inflight')

    def __init__(self) -> None:
        self.inflight: str | None = None
        self.done = asyncio.Event()


class CheckoutSerializer:
    """One checkout at a time per user, with replay of the payment just created.

    The bot keeps a single «current cart» slot per user: two parallel checkouts would
    overwrite each other's cart and ``bind_cart_to_payment``, and the first payment would
    stop matching its cart (the money would hang on the balance). So:

    * the first request for a user claims the slot and runs the checkout to completion
      (clear slot → save cart → create payment → bind cart to payment);
    * a parallel request with the SAME fingerprint waits for the first one and replays its
      payment — the person gets the same payment link in both tabs, never a second payment
      for the one cart;
    * a parallel request with a DIFFERENT cart gets 'busy' right away — letting it wait and
      then overwrite the slot mid-flight is exactly the broken state this class prevents;
    * after the checkout finished, an identical retry within CHECKOUT_REPLAY_TTL_S replays
      the same payment (idempotency anchor = the payment_id of the remembered result).
    """

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._slots: dict[int, _CheckoutSlot] = {}
        self._recent: dict[int, tuple[float, str, dict[str, Any]]] = {}

    async def begin(self, user_id: int, fingerprint: str) -> tuple[str, asyncio.Event | None]:
        """'locked' — the slot is ours until ``end``; 'wait' — the same checkout is in flight,
        await the returned event, then ``replay``; 'busy' — a different checkout is in flight."""
        async with self._guard:
            if len(self._slots) >= _SLOTS_MAX:
                for stale_id, stale in list(self._slots.items()):
                    if stale.inflight is None:
                        del self._slots[stale_id]
            slot = self._slots.get(user_id)
            if slot is None:
                slot = _CheckoutSlot()
                self._slots[user_id] = slot
            if slot.inflight is not None:
                if slot.inflight == fingerprint:
                    return 'wait', slot.done
                return 'busy', None
            slot.inflight = fingerprint
            slot.done = asyncio.Event()
            return 'locked', None

    async def end(self, user_id: int) -> None:
        async with self._guard:
            slot = self._slots.get(user_id)
            if slot is None:
                return
            # Wake the same-fingerprint waiters BEFORE releasing the claim: they replay the
            # remembered payment, and a fresh checkout may start right after.
            slot.done.set()
            slot.inflight = None

    def remember(self, user_id: int, fingerprint: str, result: dict[str, Any]) -> None:
        if len(self._recent) >= _RECENT_MAX:
            now = time.monotonic()
            for key, (expires_at, _, _) in list(self._recent.items()):
                if expires_at <= now:
                    del self._recent[key]
        self._recent[user_id] = (time.monotonic() + CHECKOUT_REPLAY_TTL_S, fingerprint, result)

    def replay(self, user_id: int, fingerprint: str) -> dict[str, Any] | None:
        """The remembered result of an identical checkout, if it is still within the replay window."""
        entry = self._recent.get(user_id)
        if entry is None:
            return None
        expires_at, saved, result = entry
        if expires_at <= time.monotonic() or saved != fingerprint:
            return None
        return result


checkout_serializer = CheckoutSerializer()

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
