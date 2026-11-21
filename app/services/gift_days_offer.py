from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select

from app.database.crud.subscription import extend_subscription, get_subscription_by_user_id
from app.database.models import (
    DiscountOffer,
    PromoOfferLog,
    SubscriptionStatus,
    Transaction,
    TransactionType,
    User,
)
from app.localization.texts import get_texts
from app.utils.formatters import format_human_date
from app.utils.lifetime import is_lifetime_end, is_lifetime_period
from app.utils.timezone import get_local_timezone


logger = structlog.get_logger(__name__)

EFFECT_TYPE = 'bonus_days'
TRIAL_GIFT_SOURCE = 'trial_gift_3m'
MIN_DAYS = 90
BONUS_DAYS = 90

_PERIOD = re.compile(r'\bна (\d+) дн')
_INTERVAL_SECONDS = 60
_SETTLE = timedelta(seconds=30)
_GRACE = timedelta(days=2)
_RETRY = timedelta(days=7)
_LIVE = (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.LIMITED.value)


@dataclass(frozen=True)
class PeriodGift:
    offer_id: int
    min_days: int
    bonus_days: int
    expires_at: datetime

    def days_for(self, period_days: int | None) -> int:
        if period_days is None or is_lifetime_period(period_days) or int(period_days) < self.min_days:
            return 0
        return self.bonus_days


def purchased_days(description: str | None) -> int | None:
    match = _PERIOD.search(description or '')
    return int(match.group(1)) if match else None


def human_date(moment: datetime, language: str = 'ru', now: datetime | None = None) -> str:
    local = moment.astimezone(get_local_timezone())
    text = format_human_date(local, language)
    return text if local.year == (now or datetime.now(UTC)).astimezone(local.tzinfo).year else f'{text} {local.year}'


def months_text(days: int, *, short: bool = False) -> str:
    months = round(days / 30)
    if not months:
        return f'{days} дн.'
    if short:
        return f'{months} мес.'
    tail = months % 100
    word = (
        'месяцев'
        if 11 <= tail <= 14
        else {1: 'месяц', 2: 'месяца', 3: 'месяца', 4: 'месяца'}.get(months % 10, 'месяцев')
    )
    return f'{months} {word}'


def gift_payload(gift: PeriodGift | None) -> dict | None:
    if gift is None:
        return None
    return {'min_days': gift.min_days, 'bonus_days': gift.bonus_days, 'expires_at': gift.expires_at.isoformat()}


def _gift(offer: DiscountOffer) -> PeriodGift:
    data = offer.extra_data or {}
    return PeriodGift(
        offer_id=offer.id,
        min_days=int(data.get('min_days', MIN_DAYS)),
        bonus_days=int(data.get('bonus_days', BONUS_DAYS)),
        expires_at=offer.expires_at,
    )


async def active_gift(db, user_id: int | None, now: datetime | None = None) -> PeriodGift | None:
    if not user_id:
        return None
    now = now or datetime.now(UTC)
    query = (
        select(DiscountOffer)
        .where(
            DiscountOffer.user_id == user_id,
            DiscountOffer.effect_type == EFFECT_TYPE,
            DiscountOffer.is_active.is_(True),
            DiscountOffer.claimed_at.is_(None),
            DiscountOffer.expires_at > now,
        )
        .order_by(DiscountOffer.expires_at.desc())
        .limit(1)
    )
    try:
        async with db.begin_nested():
            offer = (await db.execute(query)).scalar_one_or_none()
    except Exception as error:
        logger.warning('Подарочные дни: предложение не прочитано', user_id=user_id, error=str(error))
        return None
    return _gift(offer) if offer else None


async def grant(
    db,
    user_ids: list[int],
    *,
    expires_at: datetime,
    source: str = TRIAL_GIFT_SOURCE,
    min_days: int = MIN_DAYS,
    bonus_days: int = BONUS_DAYS,
) -> int:
    if expires_at <= datetime.now(UTC):
        raise ValueError('expires_at в прошлом')
    have = set(
        (
            await db.execute(
                select(DiscountOffer.user_id).where(
                    DiscountOffer.user_id.in_(user_ids), DiscountOffer.notification_type == source
                )
            )
        ).scalars()
    )
    fresh = [uid for uid in dict.fromkeys(user_ids) if uid not in have]
    for uid in fresh:
        db.add(
            DiscountOffer(
                user_id=uid,
                notification_type=source,
                discount_percent=0,
                bonus_amount_kopeks=0,
                expires_at=expires_at,
                is_active=True,
                effect_type=EFFECT_TYPE,
                extra_data={'min_days': min_days, 'bonus_days': bonus_days},
            )
        )
    await db.commit()
    return len(fresh)


class GiftDaysService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._bot: Bot | None = None

    def set_bot(self, bot: Bot) -> None:
        self._bot = bot

    def start_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name='gift-days')

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        while True:
            try:
                stats = await self.run_once()
                if any(stats.values()):
                    logger.info('Подарочные дни', **stats)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error('Подарочные дни: ошибка прохода', error=str(error), exc_info=True)
            await asyncio.sleep(_INTERVAL_SECONDS)

    async def run_once(self, now: datetime | None = None, sessions=None) -> dict[str, int]:
        if sessions is None:
            from app.database.database import AsyncSessionLocal

            sessions = AsyncSessionLocal

        now = now or datetime.now(UTC)
        stats = {'granted': 0, 'waiting': 0, 'failed': 0, 'panel': 0, 'notified': 0}
        async with sessions() as db:
            due = await self._due(db, now)
            unfinished = await self._unfinished(db, now)
        for offer_id, transaction_id, period in due:
            try:
                async with sessions() as db:
                    if await self._grant_one(db, offer_id, transaction_id, period, now):
                        stats['granted'] += 1
                        unfinished.append(offer_id)
                    else:
                        stats['waiting'] += 1
            except asyncio.CancelledError:
                raise
            except Exception as error:
                stats['failed'] += 1
                logger.warning('Подарочные дни не начислены', offer_id=offer_id, error=str(error))
        for offer_id in dict.fromkeys(unfinished):
            try:
                async with sessions() as db:
                    panel, notified = await self._finish(db, offer_id)
                stats['panel'] += panel
                stats['notified'] += notified
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning('Подарочные дни: панель или сообщение не прошли', offer_id=offer_id, error=str(error))
        return stats

    @staticmethod
    async def _due(db, now: datetime) -> list[tuple[int, int, int]]:
        rows = await db.execute(
            select(DiscountOffer.id, DiscountOffer.extra_data, Transaction.id, Transaction.description)
            .join(Transaction, Transaction.user_id == DiscountOffer.user_id)
            .where(
                DiscountOffer.effect_type == EFFECT_TYPE,
                DiscountOffer.claimed_at.is_(None),
                DiscountOffer.expires_at > now - _GRACE,
                or_(DiscountOffer.is_active.is_(True), DiscountOffer.expires_at <= now),
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
                Transaction.is_completed.is_(True),
                Transaction.amount_kopeks < 0,
                Transaction.created_at >= DiscountOffer.created_at,
                Transaction.created_at <= DiscountOffer.expires_at,
                Transaction.created_at <= now - _SETTLE,
            )
            .order_by(Transaction.created_at)
        )
        picked: dict[int, tuple[int, int, int]] = {}
        for offer_id, data, transaction_id, description in rows:
            period = purchased_days(description)
            min_days = int((data or {}).get('min_days', MIN_DAYS))
            if offer_id in picked or period is None or is_lifetime_period(period) or period < min_days:
                continue
            picked[offer_id] = (offer_id, transaction_id, period)
        return list(picked.values())

    @staticmethod
    async def _unfinished(db, now: datetime) -> list[int]:
        rows = await db.execute(
            select(DiscountOffer.id, DiscountOffer.extra_data).where(
                DiscountOffer.effect_type == EFFECT_TYPE,
                DiscountOffer.claimed_at > now - _RETRY,
            )
        )
        return [
            offer_id
            for offer_id, data in rows
            if data and data.get('granted') and not (data.get('panel_synced') and data.get('notified'))
        ]

    @staticmethod
    async def _grant_one(db, offer_id: int, transaction_id: int, period: int, now: datetime) -> bool:
        offer = (
            await db.execute(
                select(DiscountOffer).where(DiscountOffer.id == offer_id).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if offer is None or offer.claimed_at is not None:
            return False
        subscription = await get_subscription_by_user_id(db, offer.user_id)
        if (
            subscription is None
            or subscription.is_trial
            or subscription.status not in _LIVE
            or subscription.end_date is None
            or subscription.end_date <= now
            or is_lifetime_end(subscription.end_date)
        ):
            await db.rollback()
            return False
        gift = _gift(offer)
        old_end = subscription.end_date
        await extend_subscription(db, subscription, gift.bonus_days, commit=False, new_term=False)
        offer.claimed_at = now
        offer.is_active = False
        offer.extra_data = {
            **(offer.extra_data or {}),
            'granted': True,
            'transaction_id': transaction_id,
            'period_days': period,
            'subscription_id': subscription.id,
            'old_end': old_end.isoformat(),
            'new_end': subscription.end_date.isoformat(),
            'panel_synced': False,
            'notified': False,
        }
        db.add(
            PromoOfferLog(
                user_id=offer.user_id,
                offer_id=offer.id,
                action='claimed',
                source=offer.notification_type,
                effect_type=EFFECT_TYPE,
                details={'transaction_id': transaction_id, 'period_days': period, 'bonus_days': gift.bonus_days},
            )
        )
        await db.commit()
        logger.info(
            'Подарочные дни начислены',
            user_id=offer.user_id,
            offer_id=offer.id,
            period_days=period,
            bonus_days=gift.bonus_days,
        )
        return True

    async def _finish(self, db, offer_id: int) -> tuple[int, int]:
        from app.services.subscription_service import SubscriptionService

        offer = (
            await db.execute(
                select(DiscountOffer).where(DiscountOffer.id == offer_id).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if offer is None:
            return 0, 0
        data = dict(offer.extra_data or {})
        subscription = await get_subscription_by_user_id(db, offer.user_id)
        panel = notified = 0
        if not data.get('panel_synced') and subscription is not None:
            if await SubscriptionService().update_remnawave_user(db, subscription) is not None:
                data['panel_synced'] = True
                panel = 1
        if data.get('panel_synced') and not data.get('notified'):
            user = await db.get(User, offer.user_id)
            if user is None or not user.telegram_id or self._bot is None:
                data['notified'] = True
            elif subscription is not None and await self._notify(user, data['bonus_days'], subscription.end_date):
                data['notified'] = True
                notified = 1
        offer.extra_data = data
        await db.commit()
        return panel, notified

    async def _notify(self, user: User, bonus_days: int, end_date: datetime) -> bool:
        texts = get_texts(user.language)
        text = texts.t(
            'GIFT_DAYS_GRANTED',
            '🎁 Подарок начислен: +{months} к подписке. Теперь она действует до {date}.',
        ).format(months=months_text(bonus_days), date=human_date(end_date, user.language))
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.t('GIFT_DAYS_OPEN_SUBSCRIPTION', 'Моя подписка'),
                        callback_data='menu_subscription',
                    )
                ]
            ]
        )
        try:
            await self._bot.send_message(user.telegram_id, text, reply_markup=keyboard)
            return True
        except TelegramAPIError as error:
            logger.info('Подарочные дни: сообщение не доставлено', user_id=user.id, error=str(error))
            return 'blocked' in str(error).lower() or 'not found' in str(error).lower()


gift_days_service = GiftDaysService()
