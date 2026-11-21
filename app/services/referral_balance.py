from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.referral import not_referee_directed
from app.database.models import ReferralEarning, User, WithdrawalRequest, WithdrawalRequestStatus


@dataclass(frozen=True)
class ReferralBalance:
    earned_kopeks: int
    earned_days: int
    withdrawn_kopeks: int
    pending_kopeks: int
    available_kopeks: int


async def get_referral_balance(db: AsyncSession, user: User) -> ReferralBalance:
    earned, earned_days = (
        await db.execute(
            select(
                func.coalesce(func.sum(ReferralEarning.amount_kopeks), 0),
                func.coalesce(func.sum(ReferralEarning.days_granted), 0),
            ).where(ReferralEarning.user_id == user.id, not_referee_directed())
        )
    ).one()
    withdrawn = (
        await db.execute(
            select(func.coalesce(func.sum(WithdrawalRequest.amount_kopeks), 0)).where(
                WithdrawalRequest.user_id == user.id,
                WithdrawalRequest.status.in_(
                    [WithdrawalRequestStatus.APPROVED.value, WithdrawalRequestStatus.COMPLETED.value]
                ),
            )
        )
    ).scalar() or 0
    pending = (
        await db.execute(
            select(func.coalesce(func.sum(WithdrawalRequest.amount_kopeks), 0)).where(
                WithdrawalRequest.user_id == user.id,
                WithdrawalRequest.status == WithdrawalRequestStatus.PENDING.value,
            )
        )
    ).scalar() or 0
    entitlement = max(0, earned - withdrawn - pending)
    return ReferralBalance(
        earned_kopeks=earned,
        earned_days=int(earned_days or 0),
        withdrawn_kopeks=withdrawn,
        pending_kopeks=pending,
        available_kopeks=min(user.balance_kopeks, entitlement),
    )
