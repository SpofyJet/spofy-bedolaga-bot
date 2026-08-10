"""Activation funnel — automatic nudges for silent users.

Three triggers, each sent once per user (dedup via SubscriptionEvent):
  1. funnel_no_trial_1  — registered FUNNEL_NUDGE1_HOURS ago, never had any
                          subscription -> "your free trial is waiting".
  2. funnel_no_trial_2  — registered FUNNEL_NUDGE2_HOURS ago, still nothing
                          -> urgency / social proof.
  3. funnel_trial_idle  — trial is ACTIVE but traffic == 0 for
                          FUNNEL_IDLE_TRIAL_HOURS -> connection help.

Lookback windows protect the existing silent user base from a mass blast
on first deploy: only users registered within the window are targeted.
Older users are reachable via the manual broadcast segments.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.config import settings
from app.database.crud.discount_offer import upsert_discount_offer
from app.database.models import (
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
    User,
    UserStatus,
)
from app.localization.texts import get_texts
from app.utils.timezone import format_local_datetime


logger = structlog.get_logger(__name__)

# Tunables (override via env through Settings if added there; safe defaults here)
NUDGE1_HOURS = int(getattr(settings, 'FUNNEL_NUDGE1_HOURS', 2))
NUDGE2_HOURS = int(getattr(settings, 'FUNNEL_NUDGE2_HOURS', 24))
IDLE_TRIAL_HOURS = int(getattr(settings, 'FUNNEL_IDLE_TRIAL_HOURS', 3))
NUDGE1_WINDOW_HOURS = int(getattr(settings, 'FUNNEL_NUDGE1_WINDOW_HOURS', 48))
NUDGE2_WINDOW_HOURS = int(getattr(settings, 'FUNNEL_NUDGE2_WINDOW_HOURS', 168))
BATCH_LIMIT = int(getattr(settings, 'FUNNEL_BATCH_LIMIT', 50))

EVENT_NO_TRIAL_1 = 'funnel_no_trial_1'
EVENT_NO_TRIAL_2 = 'funnel_no_trial_2'
EVENT_TRIAL_IDLE = 'funnel_trial_idle'
EVENT_TRIAL_EXP_1 = 'funnel_trial_exp_1'
EVENT_TRIAL_EXP_2 = 'funnel_trial_exp_2'

TRIAL_EXP1_HOURS = int(getattr(settings, 'FUNNEL_TRIAL_EXP1_HOURS', 2))
TRIAL_EXP2_HOURS = int(getattr(settings, 'FUNNEL_TRIAL_EXP2_HOURS', 48))
TRIAL_EXP1_PERCENT = int(getattr(settings, 'FUNNEL_TRIAL_EXP1_PERCENT', 15))
TRIAL_EXP2_PERCENT = int(getattr(settings, 'FUNNEL_TRIAL_EXP2_PERCENT', 25))
TRIAL_EXP_VALID_HOURS = int(getattr(settings, 'FUNNEL_TRIAL_EXP_VALID_HOURS', 24))
TRIAL_EXP_WINDOW_HOURS = int(getattr(settings, 'FUNNEL_TRIAL_EXP_WINDOW_HOURS', 168))

EVENT_TRIAL_ENDING = 'funnel_trial_ending_1d'
EVENT_TRIAL_IDLE_2 = 'funnel_trial_idle_2'
TRIAL_ENDING_LEAD_HOURS = int(getattr(settings, 'FUNNEL_TRIAL_ENDING_LEAD_HOURS', 24))
TRIAL_ENDING_MIN_HOURS = int(getattr(settings, 'FUNNEL_TRIAL_ENDING_MIN_HOURS', 3))
IDLE_TRIAL2_HOURS = int(getattr(settings, 'FUNNEL_IDLE_TRIAL2_HOURS', 24))

EVENT_ACTIVE_TRIAL = 'funnel_active_trial'
ACTIVE_TRIAL_NUDGE_HOURS = int(getattr(settings, 'FUNNEL_ACTIVE_TRIAL_HOURS', 12))
ACTIVE_TRIAL_NUDGE_WINDOW_HOURS = int(getattr(settings, 'FUNNEL_ACTIVE_TRIAL_WINDOW_HOURS', 48))

EVENT_ABANDONED_TOPUP = 'funnel_abandoned_topup'
ABANDONED_TOPUP_MIN_AGE_HOURS = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_MIN_AGE_HOURS', 4))
ABANDONED_TOPUP_WINDOW_HOURS = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_WINDOW_HOURS', 48))
ABANDONED_TOPUP_RESEND_HOURS = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_RESEND_HOURS', 24))
NUDGE_GLOBAL_COOLDOWN_HOURS = int(getattr(settings, 'FUNNEL_GLOBAL_COOLDOWN_HOURS', 20))


def _funnel_enabled() -> bool:
    return bool(getattr(settings, 'FUNNEL_NUDGES_ENABLED', True))


def _event_sent_clause(event_type: str, min_age_hours: int = 0):
    conditions = [
        SubscriptionEvent.user_id == User.id,
        SubscriptionEvent.event_type == event_type,
    ]
    if min_age_hours > 0:
        conditions.append(SubscriptionEvent.occurred_at <= datetime.now(UTC) - timedelta(hours=min_age_hours))
    return exists(select(SubscriptionEvent.id).where(*conditions))


async def _record_event(db: AsyncSession, user_id: int, event_type: str, subscription_id: int | None = None) -> None:
    db.add(
        SubscriptionEvent(
            user_id=user_id,
            event_type=event_type,
            subscription_id=subscription_id,
            message='activation funnel nudge',
            occurred_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def _already_nudged_recently(db: AsyncSession, user_id: int) -> bool:
    """Глобальный анти-спам: любое касание воронки за последние N часов -> пропуск."""
    since = datetime.now(UTC) - timedelta(hours=NUDGE_GLOBAL_COOLDOWN_HOURS)
    result = await db.execute(
        select(
            exists().where(
                SubscriptionEvent.user_id == user_id,
                SubscriptionEvent.event_type.like('funnel_%'),
                SubscriptionEvent.created_at > since,
            )
        )
    )
    return bool(result.scalar())


async def _resolve_trial_days(db: AsyncSession) -> int:
    """Actual trial duration: trial tariff overrides env (mirrors purchase.py logic)."""
    days = settings.TRIAL_DURATION_DAYS
    if settings.is_tariffs_mode():
        try:
            from app.database.crud.tariff import get_tariff_by_id, get_trial_tariff

            trial_tariff = await get_trial_tariff(db)
            if not trial_tariff:
                trial_tariff_id = settings.get_trial_tariff_id()
                if trial_tariff_id > 0:
                    trial_tariff = await get_tariff_by_id(db, trial_tariff_id)
            if trial_tariff and getattr(trial_tariff, 'trial_duration_days', None):
                days = trial_tariff.trial_duration_days
        except Exception as error:  # noqa: BLE001
            logger.debug('Не удалось получить триальный тариф для funnel', error=str(error))
    return days


class ActivationFunnelService:
    """Periodic check, designed to be called from MonitoringService cycle."""

    def __init__(self, bot=None, send_func=None):
        # send_func: monitoring_service._send_message_with_logo (chat_id, text, reply_markup, parse_mode, user)
        self.bot = bot
        self._send = send_func
        self._trial_days: int | None = None

    async def process(self, db: AsyncSession) -> None:
        if not _funnel_enabled() or not self._send:
            return
        try:
            self._trial_days = await _resolve_trial_days(db)
            await self._nudge_no_trial(db, EVENT_NO_TRIAL_1, NUDGE1_HOURS, NUDGE1_WINDOW_HOURS, wave=1)
            await self._nudge_no_trial(db, EVENT_NO_TRIAL_2, NUDGE2_HOURS, NUDGE2_WINDOW_HOURS, wave=2)
            await self._nudge_idle_trial(db)
            await self._nudge_idle_trial_2(db)
            await self._nudge_active_trial(db)
            await self._nudge_trial_ending(db)
            await self._nudge_abandoned_topup(db)
            await self._nudge_expired_trial(db, EVENT_TRIAL_EXP_1, TRIAL_EXP1_HOURS, TRIAL_EXP1_PERCENT, wave=1)
            await self._nudge_expired_trial(db, EVENT_TRIAL_EXP_2, TRIAL_EXP2_HOURS, TRIAL_EXP2_PERCENT, wave=2)
        except Exception as error:  # noqa: BLE001 — funnel must never break the cycle
            logger.error('Ошибка activation funnel', error=error, exc_info=True)

    # --- nudge 1 & 2: registered, never had any subscription -------------

    async def _nudge_no_trial(self, db: AsyncSession, event_type: str, after_hours: int, window_hours: int, wave: int) -> None:
        now = datetime.now(UTC)
        upper = now - timedelta(hours=after_hours)        # registered at least N hours ago
        lower = now - timedelta(hours=window_hours)       # but within the lookback window

        has_any_subscription = exists(
            select(Subscription.id).where(Subscription.user_id == User.id)
        )

        result = await db.execute(
            select(User)
            .where(
                and_(
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.created_at <= upper,
                    User.created_at >= lower,
                    User.has_had_paid_subscription == False,  # noqa: E712
                    ~has_any_subscription,
                    ~_event_sent_clause(event_type),
                    # wave 2 only after wave 1 actually went out
                    _event_sent_clause(EVENT_NO_TRIAL_1, min_age_hours=max(1, NUDGE2_HOURS - NUDGE1_HOURS - 2)) if wave == 2 else True,
                )
            )
            .limit(BATCH_LIMIT)
        )
        users = result.scalars().all()

        for user in users:
            if await _already_nudged_recently(db, user.id):
                continue
            texts = get_texts(user.language)
            if wave == 1:
                text = texts.get(
                    'FUNNEL_NO_TRIAL_1',
                    (
                        '🎁 <b>Ваш бесплатный VPN ждёт активации</b>\n\n'
                        'Вы зарегистрировались, но так и не включили пробный период — '
                        'он уже ваш, платить не нужно.\n\n'
                        '⚡ {days} дн. полного доступа: все серверы, максимальная скорость.\n'
                        'Активация — одна кнопка, 10 секунд.'
                    ),
                ).format(days=self._trial_days or settings.TRIAL_DURATION_DAYS)
            else:
                text = texts.get(
                    'FUNNEL_NO_TRIAL_2',
                    (
                        '⏳ <b>Бесплатный доступ всё ещё не активирован</b>\n\n'
                        'YouTube, Instagram и Discord открываются за 10 секунд — '
                        'тысячи пользователей уже подключились.\n\n'
                        '🎁 Пробный период ничего не стоит. Попробуйте — '
                        'если не понравится, просто не продлевайте.'
                    ),
                )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.MENU_TRIAL, callback_data='menu_trial')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, event_type)
            except Exception as error:  # noqa: BLE001
                # Forbidden/blocked etc. — record anyway, do not retry forever
                logger.debug('Funnel nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, event_type)

        if users:
            logger.info('🪝 Funnel: отправлены nudge по неактивированному триалу', wave=wave, count=len(users))

    # --- nudge 3: trial activated but never connected --------------------

    async def _nudge_idle_trial(self, db: AsyncSession) -> None:
        now = datetime.now(UTC)
        activated_before = now - timedelta(hours=IDLE_TRIAL_HOURS)

        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
            .options(selectinload(Subscription.user))
            .where(
                and_(
                    Subscription.is_trial == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    func.coalesce(Subscription.traffic_used_gb, 0.0) == 0.0,
                    Subscription.created_at <= activated_before,
                    Subscription.end_date > now,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    ~_event_sent_clause(EVENT_TRIAL_IDLE),
                )
            )
            .limit(BATCH_LIMIT)
        )
        subscriptions = result.scalars().all()

        for subscription in subscriptions:
            user = subscription.user
            if not user:
                continue
            if await _already_nudged_recently(db, user.id):
                continue
            texts = get_texts(user.language)
            text = texts.get(
                'FUNNEL_TRIAL_IDLE',
                (
                    '🔌 <b>VPN активирован, но ещё не подключён</b>\n\n'
                    'Видим, что подписка включена, а трафика нет — '
                    'похоже, что-то не получилось с настройкой.\n\n'
                    'Подключение занимает 1 минуту: нажмите кнопку ниже, '
                    'выберите своё устройство и следуйте инструкции. '
                    'Если что-то не выходит — поддержка ответит быстро.'
                ),
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'), callback_data='subscription_connect')],
                    [InlineKeyboardButton(text=texts.t('MENU_SUPPORT', '🆘 Поддержка'), callback_data='menu_support')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_TRIAL_IDLE, subscription.id)
            except Exception as error:  # noqa: BLE001
                logger.debug('Funnel idle-trial nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_TRIAL_IDLE, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: отправлены nudge по неподключённому триалу', count=len(subscriptions))

    # --- nudge 4 & 5: trial expired, never paid -> discount offer ---------

    async def _nudge_expired_trial(self, db: AsyncSession, event_type: str, after_hours: int, percent: int, wave: int) -> None:
        now = datetime.now(UTC)
        upper = now - timedelta(hours=after_hours)
        lower = now - timedelta(hours=TRIAL_EXP_WINDOW_HOURS)

        ActiveSub = aliased(Subscription)
        has_active_subscription = exists(
            select(ActiveSub.id).where(
                ActiveSub.user_id == User.id,
                ActiveSub.status == SubscriptionStatus.ACTIVE.value,
            )
        )

        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
            .options(selectinload(Subscription.user))
            .where(
                and_(
                    Subscription.is_trial == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.EXPIRED.value,
                    Subscription.end_date <= upper,
                    Subscription.end_date >= lower,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.has_had_paid_subscription == False,  # noqa: E712
                    ~has_active_subscription,
                    ~_event_sent_clause(event_type),
                    _event_sent_clause(EVENT_TRIAL_EXP_1, min_age_hours=max(1, TRIAL_EXP2_HOURS - TRIAL_EXP1_HOURS - 2)) if wave == 2 else True,
                )
            )
            .limit(BATCH_LIMIT)
        )
        subscriptions = result.scalars().all()

        for subscription in subscriptions:
            user = subscription.user
            if not user:
                continue
            if await _already_nudged_recently(db, user.id):
                continue
            texts = get_texts(user.language)

            offer = await upsert_discount_offer(
                db,
                user_id=user.id,
                subscription_id=subscription.id,
                notification_type=event_type,
                discount_percent=percent,
                bonus_amount_kopeks=0,
                valid_hours=TRIAL_EXP_VALID_HOURS,
                effect_type='percent_discount',
            )

            if wave == 1:
                template = texts.get(
                    'FUNNEL_TRIAL_EXPIRED_1',
                    (
                        '🔓 <b>Тест закончился — скидка {percent}% на первую подписку</b>\n\n'
                        'Вы попробовали полную скорость и все серверы. '
                        'Чтобы доступ не пропал, держите персональную скидку <b>{percent}%</b> '
                        'на любой тариф и период.\n\n'
                        '⏰ Действует до <b>{expires_at}</b>.'
                    ),
                )
            else:
                template = texts.get(
                    'FUNNEL_TRIAL_EXPIRED_2',
                    (
                        '🎯 <b>Последний шанс: −{percent}% на первую подписку</b>\n\n'
                        'Это финальное предложение для новых пользователей — '
                        'больше скидка не вырастет.\n\n'
                        '⏰ Сгорит <b>{expires_at}</b>. После — только полная цена.'
                    ),
                )

            text = template.format(percent=percent, expires_at=format_local_datetime(offer.expires_at, '%d.%m.%Y %H:%M'))
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.t('CLAIM_DISCOUNT_BUTTON', '🎁 Забрать скидку'), callback_data=f'claim_discount_{offer.id}')],
                    [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, event_type, subscription.id)
            except Exception as error:  # noqa: BLE001
                logger.debug('Funnel trial-expired nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, event_type, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: отправлены офферы по истёкшему триалу', wave=wave, percent=percent, count=len(subscriptions))


    # --- Spofy: last-day in-trial nudge (24h before trial end) ------------

    # --- nudge: abandoned topup -------------------------------------------

    async def _nudge_abandoned_topup(self, db: AsyncSession) -> None:
        """Пользователь создал платёж, но не оплатил -> мягкое напоминание.

        Покрывает Platega (рубли) и xRocket (крипта). Пропускает тех, кто
        после этого пополнился любым способом, и не чаще раза в RESEND_HOURS.
        """
        from app.database.models import PlategaPayment, Transaction, TransactionType, XRocketPayment

        now = datetime.now(UTC)
        upper = now - timedelta(hours=ABANDONED_TOPUP_MIN_AGE_HOURS)
        lower = now - timedelta(hours=ABANDONED_TOPUP_WINDOW_HOURS)

        pending: list[tuple[User, int, str, str | None, datetime]] = []

        platega_rows = (
            await db.execute(
                select(PlategaPayment, User)
                .join(User, User.id == PlategaPayment.user_id)
                .where(
                    PlategaPayment.is_paid.is_(False),
                    PlategaPayment.status == 'PENDING',
                    PlategaPayment.created_at >= lower,
                    PlategaPayment.created_at <= upper,
                    User.telegram_id.isnot(None),
                    User.status == UserStatus.ACTIVE.value,
                )
                .limit(BATCH_LIMIT)
            )
        ).all()
        for payment, user in platega_rows:
            pay_url = payment.redirect_url
            if payment.expires_at is not None and payment.expires_at <= now:
                pay_url = None
            pending.append((user, payment.amount_kopeks, 'Platega', pay_url, payment.created_at))

        xrocket_rows = (
            await db.execute(
                select(XRocketPayment, User)
                .join(User, User.id == XRocketPayment.user_id)
                .where(
                    XRocketPayment.status == 'active',
                    XRocketPayment.created_at >= lower,
                    XRocketPayment.created_at <= upper,
                    User.telegram_id.isnot(None),
                    User.status == UserStatus.ACTIVE.value,
                )
                .limit(BATCH_LIMIT)
            )
        ).all()
        for payment, user in xrocket_rows:
            pending.append((user, payment.amount_kopeks, 'xRocket', payment.pay_url, payment.created_at))

        if not pending:
            return

        by_user: dict[int, tuple[User, int, str, str | None, datetime]] = {}
        for row in pending:
            if row[0].id not in by_user or row[4] > by_user[row[0].id][4]:
                by_user[row[0].id] = row

        sent_count = 0
        for user, amount_kopeks, method_label, pay_url, created_at in by_user.values():
            if await _already_nudged_recently(db, user.id):
                continue
            if getattr(user, 'restriction_topup', False):
                continue
            paid_later = await db.execute(
                select(
                    exists().where(
                        Transaction.user_id == user.id,
                        Transaction.type == TransactionType.DEPOSIT.value,
                        Transaction.is_completed.is_(True),
                        Transaction.created_at > created_at,
                    )
                )
            )
            if paid_later.scalar():
                continue
            recent = await db.execute(
                select(
                    exists().where(
                        SubscriptionEvent.user_id == user.id,
                        SubscriptionEvent.event_type == EVENT_ABANDONED_TOPUP,
                        SubscriptionEvent.created_at > now - timedelta(hours=ABANDONED_TOPUP_RESEND_HOURS),
                    )
                )
            )
            if recent.scalar():
                continue

            texts = get_texts(user.language)
            amount_rub = amount_kopeks // 100
            text = texts.get(
                'FUNNEL_ABANDONED_TOPUP',
                (
                    '💳 <b>Пополнение не завершено</b>\n\n'
                    'Вы создали заявку на пополнение на <b>{amount}₽</b>, но оплата так и не прошла.\n\n'
                    'Если что-то пошло не так — попробуйте другой способ: СБП, карта или криптовалюта. '
                    'Оплата занимает меньше минуты.'
                ),
            ).format(amount=amount_rub, method=method_label)

            buttons = []
            if pay_url:
                buttons.append(
                    [InlineKeyboardButton(text=texts.t('FUNNEL_ABANDONED_TOPUP_PAY', '💳 Оплатить {amount}₽').format(amount=amount_rub), url=pay_url)]
                )
            buttons.append(
                [InlineKeyboardButton(text=texts.t('FUNNEL_ABANDONED_TOPUP_OTHER', '🔄 Другой способ оплаты'), callback_data='balance_topup')]
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_ABANDONED_TOPUP)
                    sent_count += 1
            except Exception as error:  # noqa: BLE001
                logger.debug('Funnel abandoned-topup не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_ABANDONED_TOPUP)

        if sent_count:
            logger.info('🪝 Funnel: напоминания о брошенной оплате', count=sent_count)

    async def _nudge_trial_ending(self, db: AsyncSession) -> None:
        now = datetime.now(UTC)
        soon = now + timedelta(hours=TRIAL_ENDING_LEAD_HOURS)
        floor = now + timedelta(hours=TRIAL_ENDING_MIN_HOURS)
        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
            .options(selectinload(Subscription.user))
            .where(
                and_(
                    Subscription.is_trial == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    Subscription.end_date <= soon,
                    Subscription.end_date > floor,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.has_had_paid_subscription == False,  # noqa: E712
                    ~_event_sent_clause(EVENT_TRIAL_ENDING),
                )
            )
            .limit(BATCH_LIMIT)
        )
        subscriptions = result.scalars().all()

        for subscription in subscriptions:
            user = subscription.user
            if not user:
                continue
            if await _already_nudged_recently(db, user.id):
                continue
            texts = get_texts(user.language)
            text = texts.get(
                'TRIAL_ENDING_1D',
                (
                    '⏳ <b>Последний день пробного периода</b>\n\n'
                    'Завтра доступ отключится — Instagram, YouTube и Spotify снова '
                    'заблокируются, а трафик станет виден провайдеру.\n\n'
                    '💎 Оформите подписку сейчас, пока пробный активен: соединение не '
                    'прервётся, настройки сохранятся.\n\n'
                    '⚡ Это займёт 1 минуту.'
                ),
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_TRIAL_ENDING, subscription.id)
            except Exception as error:  # noqa: BLE001
                logger.debug('Funnel trial-ending nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_TRIAL_ENDING, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: nudge за 24ч до конца триала', count=len(subscriptions))

    # --- Spofy: second idle-trial nudge (day 2, still no traffic) ---------

    async def _nudge_idle_trial_2(self, db: AsyncSession) -> None:
        now = datetime.now(UTC)
        activated_before = now - timedelta(hours=IDLE_TRIAL2_HOURS)
        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
            .options(selectinload(Subscription.user))
            .where(
                and_(
                    Subscription.is_trial == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    func.coalesce(Subscription.traffic_used_gb, 0.0) == 0.0,
                    Subscription.created_at <= activated_before,
                    Subscription.end_date > now,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    ~_event_sent_clause(EVENT_TRIAL_IDLE_2),
                    _event_sent_clause(EVENT_TRIAL_IDLE),
                )
            )
            .limit(BATCH_LIMIT)
        )
        subscriptions = result.scalars().all()

        for subscription in subscriptions:
            user = subscription.user
            if not user:
                continue
            if await _already_nudged_recently(db, user.id):
                continue
            texts = get_texts(user.language)
            text = texts.get(
                'TRIAL_INACTIVE_24H',
                (
                    '⏳ <b>Прошли сутки с начала теста</b>\n\n'
                    'Мы не видим трафика по вашей подписке. Загляните в инструкцию '
                    'или напишите в поддержку — поможем подключиться!'
                ),
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'), callback_data='subscription_connect')],
                    [InlineKeyboardButton(text=texts.t('MENU_SUPPORT', '🆘 Поддержка'), callback_data='menu_support')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_TRIAL_IDLE_2, subscription.id)
            except Exception as error:  # noqa: BLE001
                logger.debug('Funnel idle-trial-2 nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_TRIAL_IDLE_2, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: nudge по неподключённому триалу (день 2)', count=len(subscriptions))

    async def _nudge_active_trial(self, db: AsyncSession) -> None:
        """Триал активен, трафик есть, прошло N часов -> мягкий пуш к подписке без скидок."""
        now = datetime.now(UTC)
        activated_before = now - timedelta(hours=ACTIVE_TRIAL_NUDGE_HOURS)
        activated_after = now - timedelta(hours=ACTIVE_TRIAL_NUDGE_WINDOW_HOURS)

        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
            .options(selectinload(Subscription.user))
            .where(
                and_(
                    Subscription.is_trial == True,  # noqa: E712
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    Subscription.traffic_used_gb > 0.0,
                    Subscription.created_at <= activated_before,
                    Subscription.created_at >= activated_after,
                    Subscription.end_date > now,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.has_had_paid_subscription == False,  # noqa: E712
                    ~_event_sent_clause(EVENT_ACTIVE_TRIAL),
                )
            )
            .limit(BATCH_LIMIT)
        )
        subscriptions = result.scalars().all()

        for subscription in subscriptions:
            user = subscription.user
            if not user:
                continue
            if await _already_nudged_recently(db, user.id):
                continue
            texts = get_texts(user.language)
            days_left = max(1, (subscription.end_date - now).days)
            text = texts.get(
                'FUNNEL_ACTIVE_TRIAL_NUDGE',
                (
                    '👋 <b>Вы активно пользуетесь VPN</b>\n\n'
                    'За время пробного периода потрачено <b>{traffic_used} ГБ</b> — отличный знак.\n\n'
                    '⏳ Через {days_left} дн. тест закончится и доступ отключится. '
                    'Оформите подписку сейчас — соединение не прервётся, настройки сохранятся.'
                ),
            ).format(traffic_used=subscription.traffic_used_gb, days_left=days_left)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy')],
                    [InlineKeyboardButton(text=texts.t('MENU_SUPPORT', '🆘 Поддержка'), callback_data='menu_support')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_ACTIVE_TRIAL, subscription.id)
            except Exception as error:  # noqa: BLE001
                logger.debug('Funnel active-trial nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_ACTIVE_TRIAL, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: отправлены nudge активным триал-пользователям', count=len(subscriptions))
