"""Дни за приглашённого друга: награда обоим, когда друг реально подключил VPN.

Когда новый человек, пришедший по приглашению, впервые подключается:

* ему +2 дня к пробному периоду;
* пригласившему +2 дня к действующей подписке (не больше 4 друзей, то есть +8 дней).

Награда выдаётся только по событию «первое подключение» из панели, поэтому честная: дни получают за
настоящего пользователя, а не за регистрацию. Каждый шаг один раз на человека.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.constants import ALIVE_SUBSCRIPTION_STATUSES
from app.database.crud.subscription import extend_subscription
from app.database.models import Subscription, SubscriptionEvent, User
from app.localization.texts import get_texts
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)

EVENT_INVITED_BONUS = 'quest_invited_bonus'  # у друга: получил дни за приглашение
EVENT_FRIEND_REWARD = 'quest_friend_reward'  # у пригласившего: получил дни за друга

DAYS_FRIEND = 2  # и другу, и пригласившему
FRIEND_MAX_FRIENDS = 4  # потолок наград пригласившему: не больше +8 дней
NEW_USER_WINDOW_DAYS = 7  # «друг» — новый человек, иначе реферал-ферма из старых аккаунтов


def _enabled() -> bool:
    return bool(getattr(settings, 'TRIAL_QUESTS_ENABLED', True))


def _is_alive(subscription: Subscription | None, now: datetime) -> bool:
    if subscription is None or subscription.status not in ALIVE_SUBSCRIPTION_STATUSES:
        return False
    end = subscription.end_date
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return end is not None and end > now


async def _count_events(db: AsyncSession, user_id: int, event_type: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(SubscriptionEvent)
        .where(SubscriptionEvent.user_id == user_id, SubscriptionEvent.event_type == event_type)
    )
    return int(result.scalar() or 0)


async def _record(db: AsyncSession, user_id: int, event_type: str, subscription_id: int | None) -> None:
    db.add(
        SubscriptionEvent(
            user_id=user_id,
            event_type=event_type,
            subscription_id=subscription_id,
            message='friend reward',
            occurred_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def _add_days(db: AsyncSession, subscription: Subscription, days: int) -> None:
    """Те же два шага, что у промокода на дни: база, затем панель (триал остаётся триалом)."""
    from app.services.subscription_service import SubscriptionService

    await extend_subscription(db, subscription, days)
    await SubscriptionService().update_remnawave_user(db, subscription)


async def _send(bot, user: User, text: str, keyboard: InlineKeyboardMarkup) -> None:
    if bot is None or not user.telegram_id:
        return
    try:
        await bot.send_message(chat_id=user.telegram_id, text=text, reply_markup=keyboard, parse_mode='HTML')
    except Exception as error:
        logger.debug('Награда за друга: сообщение не доставлено', user_id=user.id, error=str(error))


async def _eligible_inviter(db: AsyncSession, friend: User, now: datetime) -> User | None:
    """Пригласивший, если друг — новый человек и у пригласившего ещё есть место в лимите наград."""
    inviter_id = getattr(friend, 'referred_by_id', None)
    if not inviter_id or inviter_id == friend.id:
        return None
    created = friend.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if created is None or now - created > timedelta(days=NEW_USER_WINDOW_DAYS):
        return None
    inviter = await db.get(User, inviter_id)
    if inviter is None or inviter.status != 'active':
        return None
    if await _count_events(db, inviter.id, EVENT_FRIEND_REWARD) >= FRIEND_MAX_FRIENDS:
        return None
    return inviter


async def _best_subscription(db: AsyncSession, user_id: int, now: datetime) -> Subscription | None:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    alive = [s for s in result.scalars().all() if _is_alive(s, now)]
    return max(alive, key=lambda s: s.end_date) if alive else None


async def on_first_connected(db: AsyncSession, user: User, subscription: Subscription | None, bot) -> bool:
    """Друг впервые подключился. Возвращает True, если награда выдана и сообщение отправлено."""
    if not _enabled() or subscription is None:
        return False
    now = datetime.now(UTC)
    if not _is_alive(subscription, now) or await _count_events(db, user.id, EVENT_INVITED_BONUS):
        return False
    inviter = await _eligible_inviter(db, user, now)
    if inviter is None:
        return False

    # Друг: +дни к пробному периоду.
    await _add_days(db, subscription, DAYS_FRIEND)
    await _record(db, user.id, EVENT_INVITED_BONUS, subscription.id)
    texts = get_texts(user.language)
    friend_text = '\n'.join(
        [
            texts.t(
                'QUEST_FRIEND_INVITEE',
                '🎁 <b>Вас пригласил друг: вам +{days} дн.</b> к пробному периоду.',
            ).format(days=DAYS_FRIEND),
            '',
            texts.t('QUEST_ACTIVE_UNTIL', 'Доступ действует до {date}.').format(
                date=format_local_datetime(subscription.end_date, '%d.%m.%Y %H:%M')
            ),
        ]
    )
    await _send(
        bot,
        user,
        friend_text,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy')],
                [InlineKeyboardButton(text=texts.MY_SUBSCRIPTION_BUTTON, callback_data='menu_subscription')],
            ]
        ),
    )

    # Пригласивший: +дни, если есть действующая подписка (воскрешать истёкшую не будем).
    inviter_subscription = await _best_subscription(db, inviter.id, now)
    if inviter_subscription is not None:
        await _add_days(db, inviter_subscription, DAYS_FRIEND)
        await _record(db, inviter.id, EVENT_FRIEND_REWARD, inviter_subscription.id)
        inviter_texts = get_texts(inviter.language)
        inviter_text = '\n'.join(
            [
                inviter_texts.t(
                    'QUEST_FRIEND_INVITER',
                    '👥 <b>Ваш друг подключился!</b> Вам зачислено <b>+{days} дн.</b>',
                ).format(days=DAYS_FRIEND),
                '',
                inviter_texts.t(
                    'QUEST_FRIEND_MORE',
                    'За каждого нового друга, который подключится, ещё +{days} дн. (до {max_friends} друзей).',
                ).format(days=DAYS_FRIEND, max_friends=FRIEND_MAX_FRIENDS),
            ]
        )
        await _send(
            bot,
            inviter,
            inviter_text,
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=inviter_texts.t('QUEST_BUTTON_INVITE', '👥 Позвать ещё друга'),
                            callback_data='menu_referrals',
                        )
                    ]
                ]
            ),
        )
    return True
