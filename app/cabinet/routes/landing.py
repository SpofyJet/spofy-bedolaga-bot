"""Public landing page routes for guest quick-purchase flow."""

import re
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cabinet.auth.registration_access import (
    evaluate_public_registration,
    raise_for_registration_decision,
)
from app.cabinet.dependencies import get_cabinet_db
from app.cabinet.ip_utils import get_client_ip
from app.config import settings
from app.database.crud.landing import get_purchase_by_token
from app.database.crud.tariff import get_tariff_by_id
from app.database.crud.user import get_user_by_email
from app.database.models import GuestPurchase, GuestPurchaseStatus
from app.services.gift_claim_service import (
    GiftClaimAlreadyOwnedError,
    GiftClaimNotActivatableError,
    GiftClaimNotFoundError,
    GiftClaimSelfActivationError,
    claim_gift_for_user,
)
from app.services.guest_purchase_service import (
    GuestPurchaseError,
    _find_or_create_user,
    activate_purchase as activate_guest_purchase,
)
from app.services.registration_access_service import RegistrationChannel
from app.utils.cache import RateLimitCache
from app.utils.gift_links import (
    build_gift_claim_artifacts,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/landing', tags=['Guest purchases'])


# ============ Schemas ============


_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_TELEGRAM_RE = re.compile(r'^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$')


class PurchaseStatusResponse(BaseModel):
    status: str
    subscription_url: str | None = None
    subscription_crypto_link: str | None = None
    is_gift: bool = False
    contact_value: str | None = None
    recipient_contact_value: str | None = None
    period_days: int | None = None
    tariff_name: str | None = None
    gift_message: str | None = None
    contact_type: str | None = None
    cabinet_email: str | None = None
    cabinet_password: str | None = None
    auto_login_token: str | None = None
    recipient_in_bot: bool | None = None
    bot_link: str | None = None
    # Gift claim link (the buyer forwards this; whoever activates it gets the gift).
    # Derived from token + status, NOT from purchase.user (which is NULL until claimed).
    is_claimable: bool = False
    claim_url: str | None = None
    bot_claim_link: str | None = None
    gift_code: str | None = None
    bot_claim_url: str | None = None
    cabinet_claim_url: str | None = None


def _validate_contact(contact_type: str, contact_value: str) -> None:
    """Validate contact value matches the declared type format."""
    if contact_type == 'email' and not _EMAIL_RE.match(contact_value):
        raise ValueError('Invalid email format')
    if contact_type == 'telegram' and not _TELEGRAM_RE.match(contact_value):
        raise ValueError('Invalid Telegram username format')


class GiftClaimRequest(BaseModel):
    """Web (email) gift claim. The token is the bearer secret; the email is the
    account the gift binds to. No auth — whoever holds the link can claim."""

    email: str = Field(min_length=3, max_length=255)

    @model_validator(mode='after')
    def validate_email(self) -> 'GiftClaimRequest':
        _validate_contact('email', self.email)
        return self


class GiftClaimResponse(BaseModel):
    """Returned to the claimer (recipient) after a successful web claim. Carries
    the connection link + one-click cabinet login — these are NOT exposed on the
    public GET endpoint, only handed to the person who just claimed."""

    status: str
    tariff_name: str | None = None
    period_days: int | None = None
    subscription_url: str | None = None
    subscription_crypto_link: str | None = None
    auto_login_token: str | None = None


# ============ Helpers ============


def _mask_contact(value: str) -> str:
    """Mask contact value to avoid leaking PII in API responses."""
    if '@' in value and not value.startswith('@'):
        # Email: show first 2 chars + mask + domain
        local, domain = value.rsplit('@', 1)
        return f'{local[:2]}***@{domain}'
    if value.startswith('@'):
        # Telegram: show first 3 chars + mask
        return f'{value[:3]}***'
    return value[:3] + '***'


_SUBSCRIPTION_URL_EXPIRY_HOURS = 24


def _build_purchase_status_response(purchase: GuestPurchase) -> PurchaseStatusResponse:
    """Build a PurchaseStatusResponse from a GuestPurchase record."""
    tariff_name = purchase.tariff.name if purchase.tariff else None

    within_ttl = False
    subscription_url = None
    subscription_crypto_link = None
    if purchase.delivered_at and purchase.subscription_url and not purchase.is_gift:
        age = datetime.now(UTC) - purchase.delivered_at
        if age < timedelta(hours=_SUBSCRIPTION_URL_EXPIRY_HOURS):
            within_ttl = True
            subscription_url = purchase.subscription_url
            subscription_crypto_link = purchase.subscription_crypto_link

    masked_contact = _mask_contact(purchase.contact_value) if purchase.contact_value else None

    recipient_contact_value = None
    gift_message = None
    if purchase.is_gift:
        if purchase.gift_recipient_value:
            recipient_contact_value = _mask_contact(purchase.gift_recipient_value)
        gift_message = purchase.gift_message

    # Determine effective contact type for the recipient
    if purchase.is_gift and purchase.gift_recipient_type:
        effective_contact_type = purchase.gift_recipient_type
    else:
        effective_contact_type = purchase.contact_type

    # Cabinet credentials for email self-purchases (not gifts)
    cabinet_email = None
    cabinet_password = None
    auto_login_token = None
    is_terminal = purchase.status in (GuestPurchaseStatus.DELIVERED.value, GuestPurchaseStatus.PENDING_ACTIVATION.value)
    is_email_self_purchase = effective_contact_type == 'email' and not purchase.is_gift

    if is_terminal and is_email_self_purchase:
        cabinet_email = purchase.contact_value
        # For PENDING_ACTIVATION: cap credential exposure at 72h from paid_at
        pending_within_ttl = (
            purchase.status == GuestPurchaseStatus.PENDING_ACTIVATION.value
            and purchase.paid_at
            and (datetime.now(UTC) - purchase.paid_at) < timedelta(hours=72)
        )
        if within_ttl or pending_within_ttl:
            cabinet_password = purchase.cabinet_password
            auto_login_token = purchase.auto_login_token

    # For telegram gifts: indicate whether recipient is known to the bot
    recipient_in_bot: bool | None = None
    bot_link: str | None = None
    if purchase.is_gift and effective_contact_type == 'telegram':
        recipient_in_bot = purchase.user is not None and purchase.user.telegram_id is not None
        if not recipient_in_bot:
            bot_username = settings.get_bot_username()
            if bot_username:
                bot_link = f'https://t.me/{bot_username}'

    # Transferable gift claim link. Derived from token + status only (NOT from
    # purchase.user, which stays NULL until someone claims). The buyer forwards
    # claim_url; whoever activates it gets the gift bound to their account.
    is_claimable = purchase.is_gift and purchase.status in (
        GuestPurchaseStatus.PAID.value,
        GuestPurchaseStatus.PENDING_ACTIVATION.value,
    )
    claim_url: str | None = None
    bot_claim_link: str | None = None
    gift_code: str | None = None
    bot_claim_url: str | None = None
    cabinet_claim_url: str | None = None

    if is_claimable:
        bot_username = settings.get_bot_username()
        cabinet_url = settings.CABINET_URL
        try:
            artifacts = build_gift_claim_artifacts(
                purchase.token,
                bot_username=bot_username,
                cabinet_url=cabinet_url,
            )
            gift_code = artifacts.public_code
            bot_claim_url = artifacts.bot_claim_url
            cabinet_claim_url = artifacts.cabinet_claim_url
            # Keep legacy fields populated with exact values for backwards compatibility
            claim_url = artifacts.cabinet_claim_url
            bot_claim_link = artifacts.bot_claim_url
        except Exception:
            # Ссылки — единственный способ передать подарок, поэтому молча отдавать
            # пустой ответ нельзя: покупатель решит, что подарок не оплатился.
            logger.exception('Failed to build gift claim artifacts', purchase_id=purchase.id)

    return PurchaseStatusResponse(
        status=purchase.status,
        subscription_url=subscription_url,
        subscription_crypto_link=subscription_crypto_link,
        is_gift=purchase.is_gift,
        contact_value=masked_contact,
        recipient_contact_value=recipient_contact_value,
        period_days=purchase.period_days,
        tariff_name=tariff_name,
        gift_message=gift_message,
        contact_type=effective_contact_type,
        cabinet_email=cabinet_email,
        cabinet_password=cabinet_password,
        auto_login_token=auto_login_token,
        recipient_in_bot=recipient_in_bot,
        bot_link=bot_link,
        is_claimable=is_claimable,
        claim_url=claim_url,
        bot_claim_link=bot_claim_link,
        gift_code=gift_code,
        bot_claim_url=bot_claim_url,
        cabinet_claim_url=cabinet_claim_url,
    )


# ============ Routes ============

# IMPORTANT: /purchase/{token} must come BEFORE /{slug} to avoid shadowing
# (FastAPI checks routes in definition order; "purchase" would match {slug})


@router.get('/purchase/{token}', response_model=PurchaseStatusResponse)
async def get_purchase_status(
    token: str,
    raw_request: Request,
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get the status of a guest purchase by token.

    No authentication required.
    """
    client_ip = get_client_ip(raw_request)
    if await RateLimitCache.is_ip_rate_limited(client_ip, 'purchase_status', limit=30, window=60, fail_closed=True):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Too many requests')

    purchase = await get_purchase_by_token(db, token)
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Purchase not found',
        )

    response = _build_purchase_status_response(purchase)

    # Cleanup: null expired credentials from DB
    needs_cleanup = False
    if purchase.delivered_at and (purchase.cabinet_password or purchase.auto_login_token):
        age = datetime.now(UTC) - purchase.delivered_at
        if age >= timedelta(hours=_SUBSCRIPTION_URL_EXPIRY_HOURS):
            needs_cleanup = True
    elif (
        purchase.status == GuestPurchaseStatus.PENDING_ACTIVATION.value
        and purchase.paid_at
        and (purchase.cabinet_password or purchase.auto_login_token)
        and (datetime.now(UTC) - purchase.paid_at) >= timedelta(hours=72)
    ):
        needs_cleanup = True

    if needs_cleanup:
        purchase.cabinet_password = None
        purchase.auto_login_token = None
        await db.commit()

    return response


@router.post('/activate/{token}', response_model=PurchaseStatusResponse)
async def activate_purchase(
    token: str,
    raw_request: Request,
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Activate a pending guest purchase, replacing the user's current subscription.

    No authentication required (token is the secret).
    """
    client_ip = get_client_ip(raw_request)
    if await RateLimitCache.is_ip_rate_limited(client_ip, 'activate_purchase', limit=5, window=60, fail_closed=True):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Too many requests')

    try:
        purchase = await activate_guest_purchase(db, token)
    except GuestPurchaseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return _build_purchase_status_response(purchase)


@router.get('/gift/{token}', response_model=PurchaseStatusResponse)
async def get_gift_claim(
    token: str,
    raw_request: Request,
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Public gift claim page data (tariff, period, message, claim links).

    No authentication required — the token is the bearer secret. Subscription
    URL / credentials are never exposed here (only to the actual claimer via the
    POST claim endpoint).
    """
    client_ip = get_client_ip(raw_request)
    if await RateLimitCache.is_ip_rate_limited(client_ip, 'gift_claim_status', limit=30, window=60, fail_closed=True):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Too many requests')

    purchase = await get_purchase_by_token(db, token)
    if purchase is None or not purchase.is_gift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Gift not found')

    return _build_purchase_status_response(purchase)


@router.post('/gift/{token}/claim', response_model=GiftClaimResponse)
async def claim_gift(
    token: str,
    body: GiftClaimRequest,
    raw_request: Request,
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Web (email) arm of the channel-agnostic gift claim.

    Binds the gift's subscription to the activator's email account and returns
    the connection link + one-click cabinet login. First-writer-wins via
    SELECT ... FOR UPDATE; the typed gift_recipient_value is never the binding
    key (whoever holds the link claims). Telegram recipients use the bot deep
    link instead of this endpoint.
    """
    client_ip = get_client_ip(raw_request)
    if await RateLimitCache.is_ip_rate_limited(client_ip, 'gift_claim', limit=5, window=60, fail_closed=True):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Too many requests')

    # Public endpoint: require the full 64-char token (no short-prefix matching,
    # which is reserved for the human-typed cabinet code path) to rule out
    # prefix collisions / enumeration.
    if len(token) < 64:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Gift not found')

    # Lock the row so concurrent claims serialize (exactly one binds).
    result = await db.execute(select(GuestPurchase).where(GuestPurchase.token == token).with_for_update())
    purchase = result.scalars().first()
    if purchase is None or not purchase.is_gift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Gift not found')

    if purchase.status not in (
        GuestPurchaseStatus.PAID.value,
        GuestPurchaseStatus.PENDING_ACTIVATION.value,
        GuestPurchaseStatus.DELIVERED.value,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='This gift cannot be activated')

    # Resolve the activator by email WITHOUT creating an account yet, so a
    # rejected claim (self-gift / already-claimed) never leaves an orphan account.
    existing_user = await get_user_by_email(db, body.email)

    # Self-activation guard — only meaningful for cabinet-originated gifts where
    # the buyer is a known account (landing buyers are anonymous → inert).
    if existing_user is not None and purchase.buyer_user_id is not None and purchase.buyer_user_id == existing_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot activate your own gift')

    # Ownership guard — already claimed by a different account.
    if purchase.user_id is not None and (existing_user is None or purchase.user_id != existing_user.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This gift has already been claimed')

    # Public web claim cannot create or revive an account while invite-only is
    # enabled — the typed email is not proof of an administrative identity. The
    # full 64-char gift token required above IS the invitation, though: it is the
    # same bearer secret the Telegram ``GIFT_`` deep link carries, so the claim is
    # admitted whenever gift links are an accepted invite (INVITE_ONLY_ALLOW_GIFT_LINKS).
    decision = await evaluate_public_registration(
        db,
        channel=RegistrationChannel.LANDING_GIFT_CLAIM,
        existing_user=existing_user,
        email=body.email,
        email_verified=False,
        verified_admin=False,
        start_parameter=f'GIFT_{token}',
    )
    raise_for_registration_decision(decision)

    # Guards passed — now create/finalize the account the gift binds to.
    user, _is_new = await _find_or_create_user(db, 'email', body.email, purchase=purchase, tariff_id=purchase.tariff_id)

    try:
        purchase = await claim_gift_for_user(
            db,
            claimant_user_id=user.id,
            claim_input=token,
            allow_legacy_short=False,
        )
    except GiftClaimNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Gift not found') from exc
    except GiftClaimAlreadyOwnedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This gift has already been claimed') from exc
    except GiftClaimSelfActivationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot activate your own gift') from exc
    except GiftClaimNotActivatableError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='This gift cannot be activated') from exc
    except GuestPurchaseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    tariff = await get_tariff_by_id(db, purchase.tariff_id)
    return GiftClaimResponse(
        status=purchase.status,
        tariff_name=tariff.name if tariff else None,
        period_days=purchase.period_days,
        subscription_url=purchase.subscription_url,
        subscription_crypto_link=purchase.subscription_crypto_link,
        auto_login_token=purchase.auto_login_token,
    )
