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
from sqlalchemy import and_, exists, func, or_, select
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
EVENT_TRIAL_FIRST_CONNECTED = 'trial_first_connected'
# trial-nudge-fix-v2: nudge ставим не позднее (триал - lead ending-1d - кулдаун),
# иначе он глушит напоминание «триал заканчивается» через глобальный 20ч кулдаун.
# Для коротких триалов (<=2д) места нет → nudge отключается (0): работает ending-1d.
# Окно выборки всегда шире порога, иначе cohort пустой и nudge молча умирает.
_TRIAL_HOURS_TOTAL = int(getattr(settings, 'TRIAL_DURATION_DAYS', 3)) * 24
_FUNNEL_COOLDOWN_H = int(getattr(settings, 'FUNNEL_GLOBAL_COOLDOWN_HOURS', 20))
_ENDING_LEAD_H = int(getattr(settings, 'FUNNEL_TRIAL_ENDING_LEAD_HOURS', 24))
_LATEST_OK_HOURS = _TRIAL_HOURS_TOTAL - _ENDING_LEAD_H - _FUNNEL_COOLDOWN_H
_ACTIVE_TRIAL_HOURS_DEFAULT = min(round(_TRIAL_HOURS_TOTAL * 0.6), _LATEST_OK_HOURS) if _LATEST_OK_HOURS >= 12 else 0
ACTIVE_TRIAL_NUDGE_HOURS = int(getattr(settings, 'FUNNEL_ACTIVE_TRIAL_HOURS', _ACTIVE_TRIAL_HOURS_DEFAULT))
ACTIVE_TRIAL_NUDGE_WINDOW_HOURS = int(
    getattr(settings, 'FUNNEL_ACTIVE_TRIAL_WINDOW_HOURS', ACTIVE_TRIAL_NUDGE_HOURS + 24)
)
if ACTIVE_TRIAL_NUDGE_WINDOW_HOURS <= ACTIVE_TRIAL_NUDGE_HOURS:
    ACTIVE_TRIAL_NUDGE_WINDOW_HOURS = ACTIVE_TRIAL_NUDGE_HOURS + 24

EVENT_ABANDONED_TOPUP = 'funnel_abandoned_topup'
# Брошенная оплата: по данным 62% людей завершают платёж сами, но почти все — в первые 10 минут
# (между 10 и 60 минутами сами доплачивают 6%), поэтому напоминаем на 10-й минуте, а не через часы.
ABANDONED_TOPUP_MIN_AGE_MINUTES = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_MIN_AGE_MINUTES', 10))
ABANDONED_TOPUP_WINDOW_MINUTES = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_WINDOW_MINUTES', 30))
ABANDONED_TOPUP_RESEND_HOURS = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_RESEND_HOURS', 24))
# Если у человека действует скидка предложения и кончается раньше, продлеваем её до этого срока.
ABANDONED_TOPUP_PRICE_LOCK_MINUTES = int(getattr(settings, 'FUNNEL_ABANDONED_TOPUP_PRICE_LOCK_MINUTES', 20))

# Брошенная покупка подписки: корзина в Redis живёт час; напоминаем через 15 минут и держим ещё 20.
EVENT_ABANDONED_CART = 'funnel_abandoned_cart'
ABANDONED_CART_MIN_AGE_SECONDS = int(getattr(settings, 'FUNNEL_ABANDONED_CART_MIN_AGE_MINUTES', 15)) * 60
ABANDONED_CART_LOCK_MINUTES = int(getattr(settings, 'FUNNEL_ABANDONED_CART_LOCK_MINUTES', 20))
ABANDONED_CART_RESEND_HOURS = int(getattr(settings, 'FUNNEL_ABANDONED_CART_RESEND_HOURS', 24))

# После покупки приглашаем позвать друга (дни за каждого подключившегося).
EVENT_REFERRAL_PROMPT = 'funnel_referral_prompt'
REFERRAL_PROMPT_MIN_AGE_MINUTES = 3
REFERRAL_PROMPT_WINDOW_MINUTES = 20
REFERRAL_PROMPT_RESEND_DAYS = int(getattr(settings, 'FUNNEL_REFERRAL_PROMPT_RESEND_DAYS', 30))
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


def _lock_discount_line(texts, user: User, now: datetime, lock_minutes: int) -> str:
    """Закрепление цены по-настоящему: действующая скидка предложения продлевается до ``lock_minutes``.

    Возвращает строку для сообщения или пустую, если скидки нет. Коммит делает вызывающий.
    """
    percent = getattr(user, 'promo_offer_discount_percent', 0) or 0
    expires = getattr(user, 'promo_offer_discount_expires_at', None)
    if percent <= 0 or expires is None:
        return ''
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    lock_until = now + timedelta(minutes=lock_minutes)
    if now < expires < lock_until:
        user.promo_offer_discount_expires_at = lock_until
        expires = lock_until
    if expires <= now:
        return ''
    minutes_left = max(1, int((expires - now).total_seconds() // 60))
    return texts.t(
        'FUNNEL_ABANDONED_TOPUP_LOCK',
        '🔒 Ваша скидка <b>{percent}%</b> закреплена за вами ещё <b>{minutes} мин</b>.',
    ).format(percent=percent, minutes=minutes_left)


def _cryptobot_payload_kopeks(payload: str | None) -> int:
    """Сумма в копейках из payload счёта CryptoBot (``balance_<user>_<копейки>``), 0 если не разобрать."""
    try:
        return max(0, int(str(payload or '').rsplit('_', 1)[-1]))
    except ValueError:
        return 0


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
        except Exception as error:
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
            await self._nudge_expired_trial(db, EVENT_TRIAL_EXP_1, TRIAL_EXP1_HOURS, TRIAL_EXP1_PERCENT, wave=1)
            await self._nudge_expired_trial(db, EVENT_TRIAL_EXP_2, TRIAL_EXP2_HOURS, TRIAL_EXP2_PERCENT, wave=2)
        except Exception as error:
            logger.error('Ошибка activation funnel', error=error, exc_info=True)

    # --- nudge 1 & 2: registered, never had any subscription -------------

    async def _nudge_no_trial(
        self, db: AsyncSession, event_type: str, after_hours: int, window_hours: int, wave: int
    ) -> None:
        now = datetime.now(UTC)
        upper = now - timedelta(hours=after_hours)  # registered at least N hours ago
        lower = now - timedelta(hours=window_hours)  # but within the lookback window

        has_any_subscription = exists(select(Subscription.id).where(Subscription.user_id == User.id))

        result = await db.execute(
            select(User)
            .where(
                and_(
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.created_at <= upper,
                    User.created_at >= lower,
                    User.has_had_paid_subscription == False,
                    ~has_any_subscription,
                    ~_event_sent_clause(event_type),
                    # wave 2 only after wave 1 actually went out
                    _event_sent_clause(EVENT_NO_TRIAL_1, min_age_hours=max(1, NUDGE2_HOURS - NUDGE1_HOURS - 2))
                    if wave == 2
                    else True,
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
                        '🎁 <b>Пробный доступ на {days} дн. ждёт вас</b>\n\n'
                        'Платить не нужно. Включается одной кнопкой за несколько секунд.'
                    ),
                ).format(days=self._trial_days or settings.TRIAL_DURATION_DAYS)
            else:
                text = texts.get(
                    'FUNNEL_NO_TRIAL_2',
                    (
                        '⏳ <b>Пробный доступ всё ещё свободен</b>\n\n'
                        'Подключитесь за минуту и проверьте, как всё работает. '
                        'Не подойдёт — просто не продлевайте.'
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
            except Exception as error:
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
                    Subscription.is_trial == True,
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
                    [
                        InlineKeyboardButton(
                            text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'), callback_data='subscription_connect'
                        )
                    ],
                    [InlineKeyboardButton(text=texts.t('MENU_SUPPORT', '🆘 Поддержка'), callback_data='menu_support')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_TRIAL_IDLE, subscription.id)
            except Exception as error:
                logger.debug('Funnel idle-trial nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_TRIAL_IDLE, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: отправлены nudge по неподключённому триалу', count=len(subscriptions))

    # --- nudge 4 & 5: trial expired, never paid -> discount offer ---------

    async def _nudge_expired_trial(
        self, db: AsyncSession, event_type: str, after_hours: int, percent: int, wave: int
    ) -> None:
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
                    Subscription.is_trial == True,
                    Subscription.status == SubscriptionStatus.EXPIRED.value,
                    Subscription.end_date <= upper,
                    Subscription.end_date >= lower,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.has_had_paid_subscription == False,
                    ~has_active_subscription,
                    ~_event_sent_clause(event_type),
                    _event_sent_clause(EVENT_TRIAL_EXP_1, min_age_hours=max(1, TRIAL_EXP2_HOURS - TRIAL_EXP1_HOURS - 2))
                    if wave == 2
                    else True,
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
                        '🎁 <b>Скидка {percent}% на первую подписку закреплена за вами</b>\n\n'
                        'Пробный период закончился. Нажмите кнопку, и скидка применится '
                        'к любому тарифу и периоду.\n\n'
                        '⏰ Действует до <b>{expires_at}</b>.'
                    ),
                )
            else:
                template = texts.get(
                    'FUNNEL_TRIAL_EXPIRED_2',
                    (
                        '⏳ <b>Скидка {percent}% скоро сгорит</b>\n\n'
                        'Мы держим её за вами, но после <b>{expires_at}</b> '
                        'останется только полная цена.'
                    ),
                )

            text = template.format(
                percent=percent, expires_at=format_local_datetime(offer.expires_at, '%d.%m.%Y %H:%M')
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=texts.t('CLAIM_DISCOUNT_BUTTON', '🎁 Забрать скидку'),
                            callback_data=f'claim_discount_{offer.id}',
                        )
                    ],
                    [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, event_type, subscription.id)
            except Exception as error:
                logger.debug('Funnel trial-expired nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, event_type, subscription.id)

        if subscriptions:
            logger.info(
                '🪝 Funnel: отправлены офферы по истёкшему триалу', wave=wave, percent=percent, count=len(subscriptions)
            )

    # --- Spofy: last-day in-trial nudge (24h before trial end) ------------

    # --- nudge: abandoned topup -------------------------------------------

    async def _abandoned_payments(self, db: AsyncSession, since: datetime, until: datetime):
        """Неоплаченные платежи за окно: ``(user, amount_kopeks, created_at)`` по всем способам с суммой."""
        from app.database.models import CryptoBotPayment, HeleketPayment, PlategaPayment, WataPayment, XRocketPayment

        rows: list[tuple[User, int, datetime]] = []
        # Telegram или подтверждённая почта (кабинет без Telegram получает письмо).
        user_ok = and_(
            User.status == UserStatus.ACTIVE.value,
            or_(User.telegram_id.isnot(None), and_(User.email.isnot(None), User.email_verified.is_(True))),
        )

        # Platega отменяет брошенный платёж сам (CANCELED), поэтому статус PENDING здесь не требуем.
        platega = await db.execute(
            select(PlategaPayment, User)
            .join(User, User.id == PlategaPayment.user_id)
            .where(
                PlategaPayment.is_paid.is_(False),
                PlategaPayment.status.in_(('PENDING', 'CANCELED')),
                PlategaPayment.created_at >= since,
                PlategaPayment.created_at <= until,
                user_ok,
            )
            .limit(BATCH_LIMIT)
        )
        rows += [(user, payment.amount_kopeks, payment.created_at) for payment, user in platega.all()]

        wata = await db.execute(
            select(WataPayment, User)
            .join(User, User.id == WataPayment.user_id)
            .where(
                WataPayment.is_paid.is_(False),
                WataPayment.status.in_(('Opened', 'Declined')),
                WataPayment.created_at >= since,
                WataPayment.created_at <= until,
                user_ok,
            )
            .limit(BATCH_LIMIT)
        )
        rows += [(user, payment.amount_kopeks, payment.created_at) for payment, user in wata.all()]

        xrocket = await db.execute(
            select(XRocketPayment, User)
            .join(User, User.id == XRocketPayment.user_id)
            .where(
                XRocketPayment.status == 'active',
                XRocketPayment.created_at >= since,
                XRocketPayment.created_at <= until,
                user_ok,
            )
            .limit(BATCH_LIMIT)
        )
        rows += [(user, payment.amount_kopeks, payment.created_at) for payment, user in xrocket.all()]

        # CryptoBot хранит сумму в монете, а рубли — в payload счёта: balance_<user>_<копейки>.
        cryptobot = await db.execute(
            select(CryptoBotPayment, User)
            .join(User, User.id == CryptoBotPayment.user_id)
            .where(
                CryptoBotPayment.status == 'active',
                CryptoBotPayment.created_at >= since,
                CryptoBotPayment.created_at <= until,
                user_ok,
            )
            .limit(BATCH_LIMIT)
        )
        for payment, user in cryptobot.all():
            kopeks = _cryptobot_payload_kopeks(payment.payload)
            if kopeks:
                rows.append((user, kopeks, payment.created_at))

        heleket = await db.execute(
            select(HeleketPayment, User)
            .join(User, User.id == HeleketPayment.user_id)
            .where(
                HeleketPayment.status.in_(('check', 'cancel')),
                HeleketPayment.currency == 'RUB',
                HeleketPayment.created_at >= since,
                HeleketPayment.created_at <= until,
                user_ok,
            )
            .limit(BATCH_LIMIT)
        )
        for payment, user in heleket.all():
            try:
                rows.append((user, round(float(payment.amount) * 100), payment.created_at))
            except (TypeError, ValueError):
                continue
        return rows

    async def process_abandoned_payments(self, db: AsyncSession) -> int:
        """Брошенная оплата: через 10 минут одно короткое сообщение с выбором способа на ту же сумму.

        Не пишем тем, кто с тех пор пополнился, и не чаще раза в сутки. Общий кулдаун воронки здесь
        не применяется: это ответ на действие человека прямо сейчас, а не плановая рассылка.
        """
        if not _funnel_enabled() or not self._send:
            return 0
        from app.database.models import Transaction, TransactionType
        from app.keyboards.inline import get_payment_methods_keyboard

        now = datetime.now(UTC)
        pending = await self._abandoned_payments(
            db,
            since=now - timedelta(minutes=ABANDONED_TOPUP_WINDOW_MINUTES),
            until=now - timedelta(minutes=ABANDONED_TOPUP_MIN_AGE_MINUTES),
        )
        if not pending:
            return 0

        latest: dict[int, tuple[User, int, datetime]] = {}
        for user, amount_kopeks, created_at in pending:
            if amount_kopeks > 0 and (user.id not in latest or created_at > latest[user.id][2]):
                latest[user.id] = (user, amount_kopeks, created_at)

        sent_count = 0
        for user, amount_kopeks, created_at in latest.values():
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

            if not user.telegram_id:
                from app.services.payment_reminder_email import send_payment_reminder_email

                sent_email = await send_payment_reminder_email(
                    email=user.email,
                    language=user.language,
                    user_id=user.id,
                    kind='payment',
                    amount_kopeks=amount_kopeks,
                )
                await _record_event(db, user.id, EVENT_ABANDONED_TOPUP)
                if sent_email:
                    sent_count += 1
                continue

            texts = get_texts(user.language)
            amount_rub = amount_kopeks // 100
            lines = [
                texts.t('FUNNEL_ABANDONED_TOPUP_TITLE', '💳 <b>Оплата не завершена</b>'),
                '',
                texts.t(
                    'FUNNEL_ABANDONED_TOPUP_BODY',
                    'Вы остановились на оплате <b>{amount} ₽</b>.\n\nНе получилось оплатить? Попробуйте другой способ.',
                ).format(amount=amount_rub),
            ]

            lock_line = _lock_discount_line(texts, user, now, ABANDONED_TOPUP_PRICE_LOCK_MINUTES)
            if lock_line:
                lines += ['', lock_line]
            text = '\n'.join(lines)

            # Кнопки способов на ту же сумму (topup_amount|метод|сумма) — без навигации пополнения.
            rows = [
                row
                for row in get_payment_methods_keyboard(amount_kopeks, user.language).inline_keyboard
                if row and all((button.callback_data or '').startswith('topup_amount|') for button in row)
            ]
            rows.append(
                [
                    InlineKeyboardButton(
                        text=texts.t('FUNNEL_ABANDONED_TOPUP_AMOUNT', '🔄 Другая сумма'),
                        callback_data='balance_topup',
                    )
                ]
            )

            try:
                sent = await self._send(
                    user.telegram_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), user=user
                )
            except Exception as error:
                logger.debug('Брошенная оплата: сообщение не доставлено', user_id=user.id, error=str(error))
                sent = None
            await _record_event(db, user.id, EVENT_ABANDONED_TOPUP)  # и commit скидки
            if sent is not None:
                sent_count += 1

        if sent_count:
            logger.info('🪝 Брошенная оплата: отправлено напоминаний', count=sent_count)
        return sent_count

    async def process_abandoned_carts(self, db: AsyncSession) -> int:
        """Брошенная покупка подписки: корзина простояла 15 минут, человек не оплатил и не вернулся.

        Корзину продлеваем на 20 минут по-настоящему и даём кнопки: оплатить недостающее и вернуться.
        """
        if not _funnel_enabled() or not self._send:
            return 0
        from app.keyboards.inline import get_payment_methods_keyboard
        from app.services.user_cart_service import user_cart_service

        now = datetime.now(UTC)
        sent_count = 0
        for user_id, cart, age_seconds in await user_cart_service.list_global_carts():
            if age_seconds < ABANDONED_CART_MIN_AGE_SECONDS:
                continue
            if cart.get('source') == 'spofy_subpage' or cart.get('cart_mode') not in ('tariff_purchase', 'extend'):
                continue
            if not cart.get('tariff_id'):
                continue
            try:
                price_kopeks = int(cart.get('total_price') or 0)
            except (TypeError, ValueError):
                continue
            if price_kopeks <= 0:
                continue
            user = await db.get(User, user_id)
            if (
                user is None
                or user.status != UserStatus.ACTIVE.value
                or getattr(user, 'restriction_topup', False)
                or not (user.telegram_id or (user.email and getattr(user, 'email_verified', False)))
            ):
                continue
            recent = await db.execute(
                select(
                    exists().where(
                        SubscriptionEvent.user_id == user.id,
                        or_(
                            and_(
                                SubscriptionEvent.event_type == EVENT_ABANDONED_CART,
                                SubscriptionEvent.created_at > now - timedelta(hours=ABANDONED_CART_RESEND_HOURS),
                            ),
                            # уже напомнили о неоплаченном платеже: второе письмо подряд не нужно
                            and_(
                                SubscriptionEvent.event_type == EVENT_ABANDONED_TOPUP,
                                SubscriptionEvent.created_at > now - timedelta(hours=1),
                            ),
                        ),
                    )
                )
            )
            if recent.scalar():
                continue

            if not user.telegram_id:
                from app.services.payment_reminder_email import send_payment_reminder_email

                await user_cart_service.extend_cart_ttl(user.id, ABANDONED_CART_LOCK_MINUTES * 60)
                sent_email = await send_payment_reminder_email(
                    email=user.email,
                    language=user.language,
                    user_id=user.id,
                    kind='cart',
                    amount_kopeks=price_kopeks,
                    description=str(cart.get('description') or ''),
                    minutes=ABANDONED_CART_LOCK_MINUTES,
                )
                await _record_event(db, user.id, EVENT_ABANDONED_CART)
                if sent_email:
                    sent_count += 1
                continue

            texts = get_texts(user.language)
            missing = max(0, price_kopeks - int(user.balance_kopeks or 0))
            await user_cart_service.extend_cart_ttl(user.id, ABANDONED_CART_LOCK_MINUTES * 60)
            lines = [
                texts.t('FUNNEL_ABANDONED_CART_TITLE', '🛒 <b>Вы остановились на покупке</b>'),
                '',
                str(cart.get('description') or ''),
                texts.t(
                    'FUNNEL_ABANDONED_CART_BODY',
                    'К оплате: <b>{price} ₽</b>. Корзина сохранена ещё <b>{minutes} мин</b>: продолжите в один шаг.',
                ).format(price=price_kopeks // 100, minutes=ABANDONED_CART_LOCK_MINUTES),
            ]
            lock_line = _lock_discount_line(texts, user, now, ABANDONED_CART_LOCK_MINUTES)
            if lock_line:
                lines += ['', lock_line]
            text = '\n'.join(line for line in lines if line is not None)

            rows = []
            if missing > 0:
                rows = [
                    row
                    for row in get_payment_methods_keyboard(missing, user.language).inline_keyboard
                    if row and all((button.callback_data or '').startswith('topup_amount|') for button in row)
                ]
            rows.append(
                [InlineKeyboardButton(text=texts.RETURN_TO_SUBSCRIPTION_CHECKOUT, callback_data='return_to_saved_cart')]
            )
            try:
                sent = await self._send(
                    user.telegram_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), user=user
                )
            except Exception as error:
                logger.debug('Брошенная корзина: сообщение не доставлено', user_id=user.id, error=str(error))
                sent = None
            await _record_event(db, user.id, EVENT_ABANDONED_CART)
            if sent is not None:
                sent_count += 1
        if sent_count:
            logger.info('🪝 Брошенная корзина: отправлено напоминаний', count=sent_count)
        return sent_count

    async def process_referral_prompt(self, db: AsyncSession) -> int:
        """Через 3 минуты после оплаты подписки: «Позовите друга — +2 дня». Раз в 30 дней на человека."""
        if not _funnel_enabled() or not self._send or not getattr(settings, 'REFERRAL_PROGRAM_ENABLED', True):
            return 0
        from app.database.models import Transaction, TransactionType
        from app.services.trial_quest_service import DAYS_FRIEND

        now = datetime.now(UTC)
        rows = await db.execute(
            select(Transaction.user_id)
            .where(
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
                Transaction.amount_kopeks < 0,
                Transaction.created_at >= now - timedelta(minutes=REFERRAL_PROMPT_WINDOW_MINUTES),
                Transaction.created_at <= now - timedelta(minutes=REFERRAL_PROMPT_MIN_AGE_MINUTES),
            )
            .distinct()
            .limit(BATCH_LIMIT)
        )
        sent_count = 0
        for (user_id,) in rows.all():
            user = await db.get(User, user_id)
            if user is None or not user.telegram_id or user.status != UserStatus.ACTIVE.value:
                continue
            recent = await db.execute(
                select(
                    exists().where(
                        SubscriptionEvent.user_id == user.id,
                        SubscriptionEvent.event_type == EVENT_REFERRAL_PROMPT,
                        SubscriptionEvent.created_at > now - timedelta(days=REFERRAL_PROMPT_RESEND_DAYS),
                    )
                )
            )
            if recent.scalar():
                continue
            texts = get_texts(user.language)
            text = '\n'.join(
                [
                    texts.t('FUNNEL_REFERRAL_PROMPT_TITLE', '👥 <b>Позовите друга — получите +{days} дн.</b>').format(
                        days=DAYS_FRIEND
                    ),
                    '',
                    texts.t(
                        'FUNNEL_REFERRAL_PROMPT_BODY',
                        'За каждого друга, который подключит VPN по вашей ссылке, вам и другу по <b>+{days} дн.</b> '
                        'Без ограничений: чем больше друзей, тем дольше доступ.',
                    ).format(days=DAYS_FRIEND),
                ]
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=texts.t('QUEST_BUTTON_INVITE', '👥 Позвать друга'), callback_data='menu_referrals'
                        )
                    ]
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
            except Exception as error:
                logger.debug('Приглашение друга: сообщение не доставлено', user_id=user.id, error=str(error))
                sent = None
            await _record_event(db, user.id, EVENT_REFERRAL_PROMPT)
            if sent is not None:
                sent_count += 1
        if sent_count:
            logger.info('🪝 Приглашение друга после оплаты: отправлено', count=sent_count)
        return sent_count

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
                    Subscription.is_trial == True,
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    Subscription.end_date <= soon,
                    Subscription.end_date > floor,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.has_had_paid_subscription == False,
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
                ('⏳ <b>Пробный период закончится завтра</b>\n\nОформите подписку сегодня, и доступ не прервётся.'),
            )
            rows = [[InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy')]]
            if settings.is_referral_program_enabled() and getattr(settings, 'TRIAL_QUESTS_ENABLED', True):
                from app.services.trial_quest_service import DAYS_FRIEND

                text += '\n\n' + texts.t(
                    'TRIAL_FRIEND_DAYS_TIP',
                    '🎁 <b>+{days} дня за друга:</b> позовите друга, и когда он подключит VPN, вам и ему по '
                    '<b>+{days} дня</b>. Без ограничений.',
                ).format(days=DAYS_FRIEND)
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=texts.t('QUEST_BUTTON_INVITE', '👥 Позвать друга'), callback_data='menu_referrals'
                        )
                    ]
                )
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_TRIAL_ENDING, subscription.id)
            except Exception as error:
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
                    Subscription.is_trial == True,
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
                    [
                        InlineKeyboardButton(
                            text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'), callback_data='subscription_connect'
                        )
                    ],
                    [InlineKeyboardButton(text=texts.t('MENU_SUPPORT', '🆘 Поддержка'), callback_data='menu_support')],
                ]
            )
            try:
                sent = await self._send(user.telegram_id, text, reply_markup=keyboard, user=user)
                if sent is not None:
                    await _record_event(db, user.id, EVENT_TRIAL_IDLE_2, subscription.id)
            except Exception as error:
                logger.debug('Funnel idle-trial-2 nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_TRIAL_IDLE_2, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: nudge по неподключённому триалу (день 2)', count=len(subscriptions))

    async def _nudge_active_trial(self, db: AsyncSession) -> None:
        """Триал активен, трафик есть, прошло N часов -> мягкий пуш к подписке без скидок."""
        if ACTIVE_TRIAL_NUDGE_HOURS <= 0:
            # trial-nudge-fix-v2: короткий триал — mid-trial nudge выключен,
            # его работу делает напоминание «триал заканчивается» (T-24ч)
            return
        now = datetime.now(UTC)
        activated_before = now - timedelta(hours=ACTIVE_TRIAL_NUDGE_HOURS)
        activated_after = now - timedelta(hours=ACTIVE_TRIAL_NUDGE_WINDOW_HOURS)

        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
            .options(selectinload(Subscription.user))
            .where(
                and_(
                    Subscription.is_trial == True,
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    or_(
                        Subscription.traffic_used_gb > 0.0,
                        _event_sent_clause(EVENT_TRIAL_FIRST_CONNECTED),
                    ),
                    Subscription.created_at <= activated_before,
                    Subscription.created_at >= activated_after,
                    Subscription.end_date > now,
                    User.status == UserStatus.ACTIVE.value,
                    User.telegram_id.isnot(None),
                    User.has_had_paid_subscription == False,
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
            traffic_used = subscription.traffic_used_gb or 0.0
            if traffic_used > 0.0:
                # trial-nudge-fix: округление до 0.1 ГБ (был сырой float в тексте)
                traffic_line = f'VPN работает, потрачено <b>{traffic_used:.1f} ГБ</b>. '
            else:
                traffic_line = ''
            # trial-nudge-fix: честный остаток дней вместо «скоро закончится»
            days_left = max(0, (subscription.end_date - now).days) if subscription.end_date else 0
            text = texts.get(
                'FUNNEL_ACTIVE_TRIAL_NUDGE',
                (
                    '{traffic_line}'
                    'Триал активен ещё {days_left} дн. Оформите подписку заранее, чтобы не потерять доступ.'
                ),
            ).format(traffic_line=traffic_line, days_left=days_left)
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
            except Exception as error:
                logger.debug('Funnel active-trial nudge не доставлен', user_id=user.id, error=str(error))
                await _record_event(db, user.id, EVENT_ACTIVE_TRIAL, subscription.id)

        if subscriptions:
            logger.info('🪝 Funnel: отправлены nudge активным триал-пользователям', count=len(subscriptions))
