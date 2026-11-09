import secrets

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import GuestPurchase, GuestPurchaseStatus


logger = structlog.get_logger(__name__)


_LANDING_UPDATABLE_FIELDS = frozenset(
    {
        'slug',
        'title',
        'subtitle',
        'is_active',
        'features',
        'footer_text',
        'allowed_tariff_ids',
        'allowed_periods',
        'payment_methods',
        'gift_enabled',
        'custom_css',
        'meta_title',
        'meta_description',
        'display_order',
        'discount_percent',
        'discount_overrides',
        'discount_starts_at',
        'discount_ends_at',
        'discount_badge_text',
        'background_config',
        'sticky_pay_button',
        'analytics_view_enabled',
        'analytics_view_goal',
        'analytics_click_enabled',
        'analytics_click_goal',
    }
)


def generate_purchase_token() -> str:
    """Generate a cryptographically secure purchase token."""
    return secrets.token_urlsafe(48)


async def create_guest_purchase(db: AsyncSession, *, commit: bool = True, **kwargs) -> GuestPurchase:
    """Create a new guest purchase with an auto-generated token."""
    if 'token' not in kwargs:
        kwargs['token'] = generate_purchase_token()

    purchase = GuestPurchase(**kwargs)
    db.add(purchase)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(purchase)
    logger.info(
        'Created guest purchase',
        purchase_id=purchase.id,
        token_length=len(purchase.token),
        status=purchase.status,
    )
    return purchase


async def get_purchase_by_token(db: AsyncSession, token: str) -> GuestPurchase | None:
    """Get a guest purchase by its token."""
    result = await db.execute(select(GuestPurchase).where(GuestPurchase.token == token))
    return result.scalars().first()


_PURCHASE_UPDATABLE_FIELDS = frozenset(
    {
        'payment_id',
        'paid_at',
        'delivered_at',
        'subscription_url',
        'subscription_crypto_link',
        'user_id',
    }
)


async def update_purchase_status(
    db: AsyncSession,
    token: str,
    status: GuestPurchaseStatus | str,
    *,
    commit: bool = True,
    **extra_fields,
) -> GuestPurchase | None:
    """Update the status of a guest purchase and optional extra fields."""
    purchase = await get_purchase_by_token(db, token)
    if purchase is None:
        return None

    old_status = purchase.status
    purchase.status = status.value if isinstance(status, GuestPurchaseStatus) else status

    for key, value in extra_fields.items():
        if key not in _PURCHASE_UPDATABLE_FIELDS:
            logger.warning('Ignoring disallowed field in purchase update', field=key)
            continue
        setattr(purchase, key, value)

    if commit:
        await db.commit()
        await db.refresh(purchase)
    else:
        await db.flush()

    logger.info(
        'Updated guest purchase status',
        purchase_id=purchase.id,
        token_length=len(token),
        old_status=old_status,
        new_status=purchase.status,
    )
    return purchase
