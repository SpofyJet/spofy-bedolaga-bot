import asyncio
import html
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database.crud.discount_offer import (
    deactivate_expired_offers,
    upsert_discount_offer,
)
from app.database.crud.notification import (
    clear_notification_by_type,
    list_sent_notification_keys,
    notification_sent,
    record_notification,
)
from app.database.crud.subscription import (
    deactivate_subscription,
    extend_subscription,
    get_expired_subscriptions,
    reactivate_subscription,
)
from app.database.crud.user import (
    cleanup_expired_promo_offer_discounts,
    get_user_by_id,
    subtract_user_balance,
)
from app.database.database import AsyncSessionLocal
from app.database.models import (
    MonitoringLog,
    Subscription,
    SubscriptionStatus,
    Ticket,
    TicketStatus,
    User,
    UserPromoGroup,
    UserStatus,
    WithdrawalRequest,
    WithdrawalRequestStatus,
)
from app.external.remnawave_api import (
    RemnaWaveAPIError,
    RemnaWaveUser,
    is_user_not_found_error,
)
from app.localization.texts import get_texts
from app.services.autopay_guard import lock_autopay_target_checked
from app.services.autopay_period import resolve_autopay_period_candidate
from app.services.notification_delivery_service import (
    NotificationType,
    notification_delivery_service,
)
from app.services.notification_settings_service import NotificationSettingsService
from app.services.panel_sync import (
    PanelAccountOwnedByAnotherUser,
    PanelSnapshot,
    is_subscription_live,
    project_onto_subscription,
    push_subscription,
    read_panel_user,
    resolve_panel_identity,
)
from app.services.promo_offer_service import promo_offer_service
from app.services.subscription_service import SubscriptionService
from app.utils.cache import cache
from app.utils.formatters import format_username_link
from app.utils.message_patch import caption_exceeds_telegram_limit
from app.utils.miniapp_buttons import build_miniapp_or_callback_button, build_subscription_extend_button
from app.utils.notification_keyboards import buy_button, keyboard
from app.utils.promo_offer import get_user_active_promo_discount_percent
from app.utils.rich_notify import try_send_rich_notification
from app.utils.subscription_time import ends_within_days
from app.utils.timezone import format_local_datetime


@dataclass
class AutopayFailState:
    """Per-(subscription, cycle) state for autopay-failure notifications.

    `cycle` is keyed on the subscription's end_date, so a successful renewal
    (which moves end_date forward) starts a fresh cycle with a fresh count.
    """

    count: int = 0
    last_sent_ts: float = 0.0
    final_sent: bool = False

    def to_dict(self) -> dict:
        return {'count': self.count, 'last_sent_ts': self.last_sent_ts, 'final_sent': self.final_sent}

    @classmethod
    def from_dict(cls, data: dict | None) -> 'AutopayFailState':
        if not data:
            return cls()
        return cls(
            count=int(data.get('count', 0)),
            last_sent_ts=float(data.get('last_sent_ts', 0.0)),
            final_sent=bool(data.get('final_sent', False)),
        )


def decide_autopay_fail_notification(
    state: AutopayFailState,
    hours_left: float,
    now_ts: float,
    *,
    max_notifications: int,
    final_reminder_hours: int,
    repeat_interval_hours: int,
) -> str | None:
    """Decide whether/what to send on a failed-autopay tick.

    Returns 'first' | 'final' | 'repeat' | None. None means stay silent this tick.
    Pure function — no I/O — so the full notification policy is unit-testable.
    """
    if max_notifications <= 0:
        return None

    # The final "subscription is about to be disconnected" reminder is the single
    # most important message, so it must be allowed even when periodic repeats have
    # already hit the per-cycle cap — it fires exactly once (guarded by final_sent).
    # No lower 0-bound on hours_left: if a coarse MONITORING_INTERVAL steps past the
    # window so the tick only lands after end_date, the still-unsent final must go.
    in_final_window = final_reminder_hours > 0 and hours_left <= final_reminder_hours

    if state.count == 0:
        # First failure of the cycle. If it already lands inside the final window,
        # send a single 'final' rather than 'first' then 'final' back-to-back.
        return 'final' if in_final_window else 'first'

    if in_final_window and not state.final_sent:
        return 'final'

    if state.count >= max_notifications:
        return None

    if repeat_interval_hours > 0 and (now_ts - state.last_sent_ts) / 3600.0 >= repeat_interval_hours:
        return 'repeat'

    return None


def apply_autopay_fail_notification(state: AutopayFailState, reason: str, now_ts: float) -> AutopayFailState:
    """Mutate state to record that a notification with `reason` was just sent."""
    state.count += 1
    state.last_sent_ts = now_ts
    if reason == 'final':
        state.final_sent = True
    return state


# Размер батча для проверки подписок на каналы (keyset pagination)
_CHANNEL_CHECK_BATCH_SIZE: int = 100


logger = structlog.get_logger(__name__)


LOGO_PATH = Path(settings.LOGO_FILE)


async def _reload_subscription(db: AsyncSession, subscription_id: int) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .options(selectinload(Subscription.user), selectinload(Subscription.tariff))
        .execution_options(populate_existing=True)
        .where(Subscription.id == subscription_id)
    )
    return result.scalar_one_or_none()


async def _rollback_quietly(db: AsyncSession, *, step: str) -> None:
    """Откат общей сессии цикла после сбоя шага.

    Шаги мониторинга идут один за другим в одной сессии. Ошибка базы оставляет
    транзакцию «сломанной», и без отката все следующие шаги цикла (напоминания,
    трафик, истечения) падают с PendingRollbackError / InFailedSQLTransaction.
    """
    try:
        await db.rollback()
    except Exception as rollback_error:
        logger.warning('Не удалось откатить сессию после ошибки шага мониторинга', step=step, error=rollback_error)


async def _fresh_record(db: AsyncSession, listed: Any, record_id: int, *, rolled_back: bool) -> Any:
    """Запись из заранее загруженного списка; после отката — перечитанная по id.

    Откат экспайрит все объекты сессии, и обращение к полям записи из старого
    списка ушло бы в ленивую подгрузку (MissingGreenlet в асинхронном коде).
    """
    if not rolled_back:
        return listed
    return await db.get(type(listed), record_id, populate_existing=True)


def _expires_by_own_date(subscription: Subscription, *, now: datetime) -> bool:
    """Подписка всё ещё та, что попала в выборку истёкших: ACTIVE с прошедшей датой."""
    end_date = subscription.end_date
    if end_date is None or subscription.status != SubscriptionStatus.ACTIVE.value:
        return False
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    return end_date <= now


TRAFFIC_WARNING_TTL_SECONDS = 45 * 86400  # дольше любого периода: ключ меняется вместе с лимитом


def traffic_warning_cache_key(subscription_id: int, traffic_limit_gb: float) -> str:
    """«Предупредили о трафике» — на подписку и текущий лимит (докупка или новый период дают новый ключ)."""
    return f'traffic_warn:{subscription_id}:{traffic_limit_gb}'


LOW_BALANCE_ALERT_TTL_SECONDS = 86400
# Заблокировавшим бота не пишем несколько дней: Telegram всё равно откажет, а без этой
# отметки попытка повторялась бы каждый цикл. Срок короткий — человек может разблокировать.
TELEGRAM_BLOCKED_TTL_SECONDS = 3 * 86400


def telegram_blocked_cache_key(telegram_id: int) -> str:
    return f'tg_blocked:{telegram_id}'


# «Автопродление не прошло» уже говорит, сколько нужно и что пополнить. Напоминание «истекает
# через N дней» в те же сутки по той же подписке — второе сообщение о том же (приходили вместе).
AUTOPAY_FAIL_NOTICE_TTL_SECONDS = 86400


def autopay_fail_notice_key(subscription_id: int) -> str:
    return f'autopay_fail_notice:{subscription_id}'


class MonitoringService:
    def __init__(self, bot=None):
        self.is_running = False
        self.subscription_service = SubscriptionService()
        self.bot = bot
        self._notified_users: set[str] = set()
        self._last_abandoned_wave2 = datetime.min.replace(tzinfo=UTC)  # вторые волны сразу при старте
        self._last_cleanup = datetime.now(UTC)
        self._sla_task = None
        self._withdrawal_reminder_task = None
        self._abandoned_payment_task = None
        self._live_menu_task = None
        # In-memory fallback состояния уведомлений об ошибке автоплатежа (на случай
        # недоступности Redis). Ключ — (subscription_id, cycle_token=int(end_date.timestamp())).
        self._autopay_fail_state: dict[tuple[int, int], dict] = {}
        # Память процесса для отметок «уже предупредили» / «бот заблокирован»: ключ → момент
        # (time.monotonic), до которого отметка действует. Страхует, когда Redis недоступен.
        self._local_marks: dict[str, float] = {}

    async def _send_message_with_logo(
        self,
        chat_id: int | None,
        text: str,
        reply_markup=None,
        parse_mode: str | None = 'HTML',
        user: User | None = None,
    ):
        """Отправляет сообщение, добавляя логотип при необходимости."""
        if not self.bot:
            raise RuntimeError('Bot instance is not available')

        # Skip email-only users (no telegram_id)
        if not chat_id:
            logger.debug('Пропуск уведомления: chat_id не указан (email-пользователь)')
            return None

        # Skip blocked/deleted users to save Telegram rate limits
        if user and user.status in (UserStatus.BLOCKED.value, UserStatus.DELETED.value):
            logger.debug('Пропуск уведомления: пользователь недоступен', user_id=user.id, status=user.status)
            return None

        # Rich-путь идёт первым, чтобы уведомления мониторинга выглядели так же, как
        # меню. Логотип не теряется: в rich он вставляется публичной ссылкой в <img>,
        # тем же способом, что и в шапке rich-меню. Таймаут тот же, что у классических
        # отправок ниже, и попытка ровно одна — иначе бюджет цикла на получателя
        # удвоился бы, а его как раз и ограничивали, чтобы цикл не залипал.
        try:
            sent_rich = await try_send_rich_notification(
                self.bot,
                chat_id,
                text,
                keyboard=reply_markup,
                with_logo=settings.ENABLE_LOGO_MODE,
                timeout=settings.MONITORING_NOTIFICATION_SEND_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                'rich-уведомление зависло дольше таймаута — пропускаем получателя, цикл продолжается',
                chat_id=chat_id,
                timeout=settings.MONITORING_NOTIFICATION_SEND_TIMEOUT,
            )
            return None
        if sent_rich:
            return None

        if (
            settings.ENABLE_LOGO_MODE
            and await asyncio.to_thread(LOGO_PATH.exists)
            and not caption_exceeds_telegram_limit(text)
        ):
            try:
                from app.utils.message_patch import _cache_logo_file_id, get_logo_media

                # Жёсткий per-send таймаут: без него залипший send_photo (на медленном
                # канале это особенно вероятно на ПЕРВОЙ отправке цикла, где грузится
                # файл логотипа ~700КБ — file_id кешируется только после успеха) держит
                # await до session timeout (60s) на каждого получателя и блокирует хвост
                # цикла мониторинга. На TimeoutError пропускаем получателя.
                result = await asyncio.wait_for(
                    self.bot.send_photo(
                        chat_id=chat_id,
                        photo=get_logo_media(),
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                    ),
                    timeout=settings.MONITORING_NOTIFICATION_SEND_TIMEOUT,
                )
                _cache_logo_file_id(result)
                return result
            except TimeoutError:
                logger.warning(
                    'send_photo завис дольше таймаута — пропускаем получателя, цикл продолжается',
                    chat_id=chat_id,
                    timeout=settings.MONITORING_NOTIFICATION_SEND_TIMEOUT,
                )
                return None
            except TelegramBadRequest as exc:
                logger.warning(
                    'Не удалось отправить сообщение с логотипом, отправляем текстовое сообщение',
                    chat_id=chat_id,
                    exc=exc,
                )

        try:
            return await asyncio.wait_for(
                self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                ),
                timeout=settings.MONITORING_NOTIFICATION_SEND_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                'send_message завис дольше таймаута — пропускаем получателя, цикл продолжается',
                chat_id=chat_id,
                timeout=settings.MONITORING_NOTIFICATION_SEND_TIMEOUT,
            )
            return None

    @staticmethod
    def _is_unreachable_error(error: TelegramBadRequest) -> bool:
        message = str(error).lower()
        unreachable_markers = (
            'chat not found',
            'user is deactivated',
            'bot was blocked by the user',
            "bot can't initiate conversation",
            "can't initiate conversation",
            'user not found',
            'peer id invalid',
        )
        return any(marker in message for marker in unreachable_markers)

    async def _handle_unreachable_user(self, user: User, error: Exception, context: str) -> bool:
        if isinstance(error, TelegramForbiddenError):
            logger.warning('⚠️ Пользователь недоступен: бот заблокирован', telegram_id=user.telegram_id, context=context)
            return True

        if isinstance(error, TelegramBadRequest) and self._is_unreachable_error(error):
            logger.warning('⚠️ Пользователь недоступен', telegram_id=user.telegram_id, context=context, error=error)
            return True

        return False

    async def start_monitoring(self):
        if self.is_running:
            logger.warning('Мониторинг уже запущен')
            return

        self.is_running = True
        logger.info('🔄 Запуск службы мониторинга')
        # Start dedicated SLA loop with its own interval for timely 5-min checks
        try:
            if not self._sla_task or self._sla_task.done():
                self._sla_task = asyncio.create_task(self._sla_loop())
        except Exception as e:
            logger.error('Не удалось запустить SLA-мониторинг', error=e)
        # Напоминания о заявках на вывод без решения — та же схема, что SLA тикетов
        try:
            if not self._withdrawal_reminder_task or self._withdrawal_reminder_task.done():
                self._withdrawal_reminder_task = asyncio.create_task(self._withdrawal_reminder_loop())
            if not self._abandoned_payment_task or self._abandoned_payment_task.done():
                self._abandoned_payment_task = asyncio.create_task(self._abandoned_payment_loop())
        except Exception as e:
            logger.error('Не удалось запустить напоминания о заявках на вывод', error=e)
        try:
            if not self._live_menu_task or self._live_menu_task.done():
                from app.services.live_menu_service import live_menu_loop

                self._live_menu_task = asyncio.create_task(live_menu_loop(self))
        except Exception as e:
            logger.error('Не удалось запустить живое меню', error=e)

        while self.is_running:
            try:
                await self._monitoring_cycle()
                await asyncio.sleep(settings.MONITORING_INTERVAL * 60)

            except Exception as e:
                logger.error('Ошибка в цикле мониторинга', error=e)
                await asyncio.sleep(60)

    def stop_monitoring(self):
        self.is_running = False
        logger.info('ℹ️ Мониторинг остановлен')
        try:
            if self._sla_task and not self._sla_task.done():
                self._sla_task.cancel()
        except Exception:
            logger.debug('Ignored error in stop_monitoring', exc_info=True)
        if self._withdrawal_reminder_task and not self._withdrawal_reminder_task.done():
            self._withdrawal_reminder_task.cancel()
        if self._abandoned_payment_task and not self._abandoned_payment_task.done():
            self._abandoned_payment_task.cancel()
        if self._live_menu_task and not self._live_menu_task.done():
            self._live_menu_task.cancel()

    async def _monitoring_cycle(self):
        async with AsyncSessionLocal() as db:
            try:
                await self._cleanup_notification_cache()

                expired_offers = await deactivate_expired_offers(db)
                if expired_offers:
                    logger.info('🧹 Деактивировано просроченных скидочных предложений', expired_offers=expired_offers)

                expired_active_discounts = await cleanup_expired_promo_offer_discounts(db)
                if expired_active_discounts:
                    logger.info(
                        '🧹 Сброшено активных скидок промо-предложений с истекшим сроком',
                        expired_active_discounts=expired_active_discounts,
                    )

                cleaned_test_access = await promo_offer_service.cleanup_expired_test_access(db)
                if cleaned_test_access:
                    logger.info(
                        '🧹 Отозвано истекших тестовых доступов к сквадам', cleaned_test_access=cleaned_test_access
                    )

                # ВАЖНО: autopay ПЕРЕД check_expired — иначе подписки с автоплатой
                # экспайрятся до того, как autopay успеет их продлить
                # Продление с баланса работает всегда, если у подписки autopay_enabled=True
                await self._process_autopayments(db)

                await self._check_expired_subscriptions(db)
                await self._check_expiring_subscriptions(db)
                await self._check_trial_expiring_soon(db)
                # Channel checks use their own batch sessions and may wait on
                # Telegram for minutes. Release the completed outer transaction
                # so PostgreSQL does not terminate it while it sits idle.
                await db.commit()
                await self._check_trial_channel_subscriptions(db)
                await self._check_expired_subscription_followups(db)
                await self._run_activation_funnel(db)
                await self._check_traffic_warnings(db)
                await self._check_low_balance_alerts(db)
                await self._expire_wheel_bonus_devices()
                await self._retry_stuck_guest_purchases(db)
                await self._cleanup_expired_refresh_tokens(db)
                await self._cleanup_button_click_logs(db)
                # Неактивных не удаляем (решение владельца 11.11.2026): удалённым рассылка
                # доходит, а повторная регистрация после /start стирает их историю.
                await self._sync_with_remnawave(db)

                await self._log_monitoring_event(
                    db,
                    'monitoring_cycle_completed',
                    'Цикл мониторинга успешно завершен',
                    {'timestamp': datetime.now(UTC).isoformat()},
                )
                await db.commit()

            except Exception as e:
                logger.error('Ошибка в цикле мониторинга', error=e)
                await _rollback_quietly(db, step='monitoring_cycle')
                try:
                    await self._log_monitoring_event(
                        db,
                        'monitoring_cycle_error',
                        f'Ошибка в цикле мониторинга: {e!s}',
                        {'error': str(e)},
                        is_success=False,
                    )
                except Exception:
                    logger.debug('Ignored error in _monitoring_cycle', exc_info=True)
                await db.rollback()

    async def _expire_wheel_bonus_devices(self) -> None:
        """Снимает устройства из колеса призов, у которых вышел срок (своя сессия, сбой не валит цикл)."""
        try:
            from app.services.wheel_service import wheel_service

            await wheel_service.expire_bonus_devices()
        except Exception as error:
            logger.warning('Не удалось снять истёкшие устройства колеса', error=str(error))

    async def _cleanup_notification_cache(self):
        current_time = datetime.now(UTC)

        if (current_time - self._last_cleanup).total_seconds() >= 3600:
            old_count = len(self._notified_users)
            self._notified_users.clear()

            # Чистим состояние autopay-fail по протухшим циклам (end_date в прошлом > 72ч)
            cutoff_ts = (current_time - timedelta(hours=72)).timestamp()
            expired_keys = [key for key in self._autopay_fail_state if key[1] < cutoff_ts]
            for key in expired_keys:
                del self._autopay_fail_state[key]
            self._purge_local_marks()

            self._last_cleanup = current_time
            logger.info(
                '🧹 Очищен кеш уведомлений',
                old_count=old_count,
                autopay_state_evicted=len(expired_keys),
                autopay_state_remaining=len(self._autopay_fail_state),
            )

    def _local_marks_store(self) -> dict[str, float]:
        marks = getattr(self, '_local_marks', None)
        if marks is None:
            marks = self._local_marks = {}
        return marks

    def _purge_local_marks(self) -> None:
        now = time.monotonic()
        marks = self._local_marks_store()
        for key in [key for key, until in marks.items() if until <= now]:
            del marks[key]

    async def _is_marked(self, key: str) -> bool:
        """Отметка есть в памяти процесса или в Redis (Redis общий с вебхуками и переживает рестарт)."""
        until = self._local_marks_store().get(key)
        if until is not None and until > time.monotonic():
            return True
        try:
            return bool(await cache.get(key))
        except Exception:
            return False

    async def _set_mark(self, key: str, ttl_seconds: int) -> None:
        """Ставит отметку в память процесса всегда и в Redis — если он доступен."""
        self._local_marks_store()[key] = time.monotonic() + ttl_seconds
        try:
            await cache.set(key, '1', expire=ttl_seconds)
        except Exception:
            logger.debug('Ignored error in _set_mark', exc_info=True)

    async def _remember_if_unreachable(self, user: User, error: Exception) -> bool:
        """Бот заблокирован / чат удалён — запомнить, чтобы не стучаться каждый цикл."""
        unreachable = isinstance(error, TelegramForbiddenError) or (
            isinstance(error, TelegramBadRequest) and self._is_unreachable_error(error)
        )
        if unreachable and user.telegram_id:
            await self._set_mark(telegram_blocked_cache_key(user.telegram_id), TELEGRAM_BLOCKED_TTL_SECONDS)
        return unreachable

    async def _load_autopay_fail_state(self, subscription_id: int, cycle_token: int) -> AutopayFailState:
        """Load per-cycle autopay-fail state. In-memory first (current within process),
        Redis as cross-restart source of truth."""
        mem = self._autopay_fail_state.get((subscription_id, cycle_token))
        if mem is not None:
            return AutopayFailState.from_dict(mem)
        try:
            data = await cache.get(f'autopay_fail:{subscription_id}:{cycle_token}')
            if data:
                return AutopayFailState.from_dict(data)
        except Exception as redis_err:
            logger.warning(
                'Ошибка чтения состояния autopay-fail из Redis, in-memory fallback',
                subscription_id=subscription_id,
                redis_err=redis_err,
            )
        return AutopayFailState()

    async def _save_autopay_fail_state(
        self, subscription_id: int, cycle_token: int, state: AutopayFailState, ttl_seconds: int
    ) -> None:
        """Persist state to in-memory (always) and Redis (best effort)."""
        self._autopay_fail_state[(subscription_id, cycle_token)] = state.to_dict()
        try:
            await cache.set(
                f'autopay_fail:{subscription_id}:{cycle_token}',
                state.to_dict(),
                expire=max(ttl_seconds, 60),
            )
        except Exception as redis_err:
            logger.warning(
                'Не удалось сохранить состояние autopay-fail в Redis, in-memory fallback активен',
                subscription_id=subscription_id,
                redis_err=redis_err,
            )

    async def _maybe_notify_autopay_failure(
        self,
        user,
        charge_amount: int,
        subscription,
        current_time: datetime,
        *,
        cause: str = 'insufficient_balance',
    ) -> None:
        """Send an autopay-failure notification iff policy allows it this tick, then
        record state. Policy = decide_autopay_fail_notification() + AUTOPAY_FAIL_* config.

        `cause` ('charge_error' | 'insufficient_balance') selects the email/non-Telegram
        reason wording so a non-balance charge failure isn't mislabelled as low balance."""
        if not NotificationSettingsService.are_notifications_globally_enabled():
            return

        cycle_token = int(subscription.end_date.timestamp())
        now_ts = current_time.timestamp()
        hours_left = (subscription.end_date - current_time).total_seconds() / 3600.0

        state = await self._load_autopay_fail_state(subscription.id, cycle_token)
        reason = decide_autopay_fail_notification(
            state,
            hours_left,
            now_ts,
            max_notifications=settings.AUTOPAY_FAIL_MAX_NOTIFICATIONS,
            final_reminder_hours=settings.AUTOPAY_FAIL_FINAL_REMINDER_HOURS,
            repeat_interval_hours=settings.AUTOPAY_FAIL_REPEAT_INTERVAL_HOURS,
        )
        if reason is None:
            return

        is_final = reason == 'final'
        delivered = False
        if user.telegram_id and self.bot:
            delivered = await self._send_autopay_failed_notification(
                user, user.balance_kopeks, charge_amount, subscription=subscription, is_final=is_final
            )
        elif not user.telegram_id:
            if is_final:
                reason_text = 'Последнее напоминание: подписка скоро отключится — недостаточно средств'
            elif cause == 'charge_error':
                reason_text = 'Ошибка списания средств'
            else:
                reason_text = 'Недостаточно средств на балансе'
            delivered = await notification_delivery_service.notify_autopay_failed(user=user, reason=reason_text)
        if delivered:
            await self._set_mark(autopay_fail_notice_key(subscription.id), AUTOPAY_FAIL_NOTICE_TTL_SECONDS)

        apply_autopay_fail_notification(state, reason, now_ts)
        ttl_seconds = int(max(0.0, hours_left) * 3600) + 72 * 3600
        await self._save_autopay_fail_state(subscription.id, cycle_token, state, ttl_seconds)

    async def _check_expired_subscriptions(self, db: AsyncSession):
        try:
            expired_subscriptions = await get_expired_subscriptions(db)

            rolled_back = False
            # Идентификаторы — заранее: после отката обращение к объектам из списка
            # полезло бы в базу ленивой подгрузкой.
            listed_pairs = [(listed.id, listed) for listed in expired_subscriptions]
            for subscription_id, listed in listed_pairs:
                try:
                    subscription = listed
                    if rolled_back:
                        # Откат сбросил загруженное: перечитываем подписку со связями,
                        # иначе ленивая подгрузка в асинхронном коде уронит и её.
                        subscription = await _reload_subscription(db, subscription_id)
                        if subscription is None:
                            continue
                    await self._expire_if_due(db, subscription)
                except Exception:
                    # Одна подписка (удалили во время прохода, панель ответила мусором) не
                    # должна останавливать гашение всех остальных.
                    logger.exception('Не удалось обработать истёкшую подписку', subscription_id=subscription_id)
                    await db.rollback()
                    rolled_back = True

            if expired_subscriptions:
                await self._log_monitoring_event(
                    db,
                    'expired_subscriptions_processed',
                    f'Обработано {len(expired_subscriptions)} истёкших подписок',
                    {'count': len(expired_subscriptions)},
                )

        except Exception as e:
            logger.error('Ошибка проверки истёкших подписок', error=e)
            await _rollback_quietly(db, step='expired_subscriptions')

    async def _expire_if_due(self, db: AsyncSession, subscription: Subscription) -> None:
        """Погасить одну подписку из выборки истёкших, если её не продлили ни в панели, ни в боте."""
        from app.database.crud.subscription import is_recently_updated_by_webhook

        if is_recently_updated_by_webhook(subscription):
            logger.debug('Пропуск expire подписки : обновлена вебхуком недавно', subscription_id=subscription.id)
            return

        # Панель — истина по сроку: продлили руками в панели, а бот ещё не читал —
        # забираем дату оттуда и не гасим.
        if await self._panel_keeps_alive(db, subscription):
            return

        from app.database.crud.subscription import expire_subscription_if_still_due

        # Capture tariff name before the expiry's db.refresh() expires the relationship
        _tariff_name = subscription.tariff.name if getattr(subscription, 'tariff', None) else None

        if not await expire_subscription_if_still_due(db, subscription):
            # Продлили в последний момент — между проверкой и записью.
            logger.info('Подписку продлили, пока её гасили, — оставляем', subscription_id=subscription.id)
            return

        user = await get_user_by_id(db, subscription.user_id)
        if user and self.bot:
            from app.utils.notification_prefs import is_subscription_expiry_enabled

            skip_notify = (
                not NotificationSettingsService.are_notifications_globally_enabled()
                or not is_subscription_expiry_enabled(user)
            )
            if not skip_notify:
                await self._send_subscription_expired_notification(user, subscription, tariff_name=_tariff_name)

        logger.info("🔴 Подписка пользователя истекла и статус изменен на 'expired'", user_id=subscription.user_id)

    async def _panel_keeps_alive(self, db: AsyncSession, subscription: Subscription) -> bool:
        """Спросить панель перед гашением по своей дате.

        Панель — истина (владелец, 2026-09-11): если аккаунт там активен и дата в
        будущем, срок продлили в обход бота (руками в панели, вебхуков нет,
        расписание раз в сутки) — берём дату и статус оттуда и подписку не гасим.
        Панель молчит, аккаунта нет или он истёк — гасим по своей дате, как раньше.

        Подписку перечитываем из базы ПОСЛЕ снимка панели. Список истёкших взят в
        начале прохода, а проход идёт с запросом в панель на каждую подписку: за это
        время человек успевает продлить, и только что продлённая подписка гасилась бы.
        """
        snapshot = await self._read_panel_before_expiry(db, subscription)
        # Всё, на чём стоит решение гасить: свой срок и статус.
        await db.refresh(subscription, ['status', 'end_date'])
        now = datetime.now(UTC)
        if not _expires_by_own_date(subscription, now=now):
            logger.info(
                'Подписку изменили, пока мониторинг шёл по списку, — не гасим',
                subscription_id=subscription.id,
                status=subscription.status,
            )
            return True
        if snapshot is None or snapshot.status != 'ACTIVE' or snapshot.expire_at is None or snapshot.expire_at <= now:
            return False
        from app.database.crud.transaction import get_last_subscription_payment_at

        paid_at = await get_last_subscription_payment_at(db, subscription.user_id)
        changed = project_onto_subscription(subscription, snapshot, now=now, paid_at=paid_at)
        if changed:
            await db.commit()
        logger.info(
            'Подписка жива в панели — срок взят оттуда, не гасим',
            subscription_id=subscription.id,
            panel_expire_at=snapshot.expire_at.isoformat(),
            changed=sorted(changed),
        )
        return True

    async def _read_panel_before_expiry(self, db: AsyncSession, subscription: Subscription) -> PanelSnapshot | None:
        """Снимок аккаунта подписки в панели; ``None`` — панель молчит или аккаунта нет."""
        service = getattr(self, 'subscription_service', None)
        if service is None or not getattr(service, 'is_configured', False):
            return None
        user = getattr(subscription, 'user', None) or await get_user_by_id(db, subscription.user_id)
        if user is None:
            return None
        try:
            async with service.get_api_client() as api:
                # С базой: аккаунт другого человека (та же почта у второй записи,
                # #3245) не наш — его оплаченный срок себе не забираем.
                identity = await resolve_panel_identity(api, user, subscription, db=db)
        except Exception as error:
            logger.warning(
                'Панель не ответила перед гашением подписки — гасим по своей дате',
                subscription_id=subscription.id,
                error=str(error)[:200],
            )
            return None
        if identity.panel_user is None:
            return None
        return read_panel_user(identity.panel_user)

    async def update_remnawave_user(self, db: AsyncSession, subscription: Subscription) -> RemnaWaveUser | None:
        try:
            from app.database.crud.subscription import is_recently_updated_by_webhook

            if is_recently_updated_by_webhook(subscription):
                logger.debug(
                    'Пропуск RemnaWave обновления подписки : обновлена вебхуком недавно',
                    subscription_id=subscription.id,
                )
                return None

            user = await get_user_by_id(db, subscription.user_id)
            panel_user_id = user.remnawave_id if user else None
            if not user or panel_user_id is None:
                logger.error('RemnaWave id не найден для пользователя', user_id=subscription.user_id)
                return None

            # Обновляем subscription в сессии, чтобы избежать detached instance
            # Загружаем tariff для определения внешнего сквада
            try:
                await db.refresh(subscription, ['tariff'])
            except Exception:
                logger.debug('Ignored error in update_remnawave_user', exc_info=True)

            # Re-check guard after refresh (webhook could have committed between first check and refresh)
            if is_recently_updated_by_webhook(subscription):
                logger.debug(
                    'Пропуск RemnaWave обновления подписки : обновлена вебхуком недавно (после refresh)',
                    subscription_id=subscription.id,
                )
                return None

            current_time = datetime.now(UTC)
            is_active = is_subscription_live(user, subscription, now=current_time)

            if subscription.status == SubscriptionStatus.ACTIVE.value and subscription.end_date <= current_time:
                # Суточные подписки управляются DailySubscriptionService — не экспайрим
                tariff = getattr(subscription, 'tariff', None)
                is_active_daily = (
                    tariff is not None
                    and getattr(tariff, 'is_daily', False)
                    and not getattr(subscription, 'is_daily_paused', False)
                )
                if is_active_daily:
                    logger.debug(
                        'update_remnawave_user: пропуск expire для суточной подписки',
                        subscription_id=subscription.id,
                    )
                else:
                    subscription.status = SubscriptionStatus.EXPIRED.value
                    await db.commit()
                    is_active = False
                    logger.info("📝 Статус подписки обновлен на 'expired'", subscription_id=subscription.id)

            if not self.subscription_service.is_configured:
                logger.warning(
                    'RemnaWave API не настроен. Пропускаем обновление пользователя', user_id=subscription.user_id
                )
                return None

            async with self.subscription_service.get_api_client() as api:
                # Сквады и внешний сквад в рутинном проходе НЕ пересылаем:
                # устаревший UUID даёт FK violation (A039), а назначаются они при
                # создании подписки. Отсюда узкий набор полей.
                result = await push_subscription(
                    api,
                    user,
                    subscription,
                    db=db,
                    only_fields={
                        'status',
                        'expire_at',
                        'traffic_limit_bytes',
                        'traffic_limit_strategy',
                        'description',
                        'hwid_device_limit',
                    },
                    verify_recorded_id=False,
                    create_if_missing=False,
                    # «Пользователя нет» разбирает ветка ниже: у неё своя проверка,
                    # что подписку вообще стоит воскрешать.
                    recreate_on_missing=False,
                    now=current_time,
                )
                updated_user = result.panel_user

                await db.commit()

                status_text = 'активным' if is_active else 'истёкшим'
                logger.info(
                    '✅ Обновлен RemnaWave пользователь со статусом',
                    remnawave_id=panel_user_id,
                    status_text=status_text,
                )
                return updated_user

        except RemnaWaveAPIError as e:
            if is_user_not_found_error(e):
                # Пользователя удалили из панели при живой подписке в боте —
                # пересоздаём (create-флоу сохранит новый id панели и ссылки в подписку).
                # RemnaWaveInvalidUserIdError сюда намеренно не попадает: битый
                # локальный идентификатор — баг в данных бота, а не «юзера нет»,
                # и уход в пересоздание плодил бы дубли в панели.
                return await self.subscription_service.recreate_deleted_panel_user(db, subscription, user=user)
            logger.error('Ошибка обновления RemnaWave пользователя', error=e)
            return None
        except PanelAccountOwnedByAnotherUser as e:
            # Две записи одного человека (#3245) — не сбой панели; оператор видит
            # предупреждение поиска, а чужой аккаунт остаётся нетронутым.
            logger.warning(
                'Аккаунт панели закреплён за другим пользователем бота — не трогаем',
                subscription_id=subscription.id,
                panel_user_id=e.panel_user_id,
                owner_user_id=e.owner_user_id,
            )
            return None
        except Exception as e:
            logger.error('Ошибка обновления RemnaWave пользователя', error=e)
            return None

    async def _check_expiring_subscriptions(self, db: AsyncSession):
        if not NotificationSettingsService.are_notifications_globally_enabled():
            return

        try:
            warning_days = settings.get_autopay_warning_days()
            all_processed_users = set()

            # n22: выборки по всем дням — один раз до цикла.
            expiring_by_days: dict[int, list] = {}
            urgent_ids_by_days: dict[int, set[int]] = {}
            # Простые значения — заранее: после отката объекты из выборок экспайрятся.
            autopay_user_ids_by_days: dict[int, list[int]] = {}
            for days in warning_days:
                expiring_by_days[days] = await self._get_expiring_paid_subscriptions(db, days)
                urgent_ids_by_days[days] = {sub.id for sub in expiring_by_days[days]}
                autopay_user_ids_by_days[days] = [sub.user_id for sub in expiring_by_days[days] if sub.autopay_enabled]

            # Отметки «уже напомнили» — одним запросом на весь проход, а не запросом на подписку.
            already_sent = await list_sent_notification_keys(
                db, set().union(*urgent_ids_by_days.values()) if urgent_ids_by_days else (), 'expiring'
            )
            rolled_back = False

            for days in warning_days:
                expiring_subscriptions = expiring_by_days[days]
                sent_count = 0

                # Batch-запрос: собираем user_id с autopay и проверяем наличие карт одним запросом

                for subscription_id, listed in [(listed.id, listed) for listed in expiring_subscriptions]:
                    try:
                        subscription = listed
                        if rolled_back:
                            # Откат сбросил загруженные объекты: перечитываем со связями.
                            subscription = await _reload_subscription(db, subscription_id)
                            if subscription is None:
                                continue
                        if await self._notify_expiring_subscription(
                            db,
                            subscription,
                            days,
                            warning_days=warning_days,
                            urgent_ids_by_days=urgent_ids_by_days,
                            already_sent=already_sent,
                            processed=all_processed_users,
                        ):
                            sent_count += 1
                    except Exception:
                        # Одна подписка не должна останавливать напоминания всем остальным.
                        logger.exception('Не удалось обработать напоминание о сроке', subscription_id=subscription_id)
                        await _rollback_quietly(db, step='expiring_subscription')
                        rolled_back = True

                if sent_count > 0:
                    await self._log_monitoring_event(
                        db,
                        'expiring_notifications_sent',
                        f'Отправлено {sent_count} уведомлений об истечении через {days} дней',
                        {'days': days, 'count': sent_count},
                    )

        except Exception as e:
            logger.error('Ошибка проверки истекающих подписок', error=e)
            await _rollback_quietly(db, step='expiring_subscriptions')

    async def _notify_expiring_subscription(
        self,
        db: AsyncSession,
        subscription: Subscription,
        days: int,
        *,
        warning_days,
        urgent_ids_by_days: dict[int, set[int]],
        already_sent: set[tuple[int, int, int | None]],
        processed: set[str],
    ) -> bool:
        """Одно напоминание «подписка истекает через N дней». True — отправили."""
        from app.utils.notification_prefs import (
            get_subscription_expiry_days,
            is_subscription_expiry_enabled,
        )

        # Пользователь уже загружен вместе с подпиской (selectinload) — без запроса на каждую.
        user = subscription.user
        if not user:
            return False

        # Respect user notification preferences
        if not is_subscription_expiry_enabled(user):
            return False

        # Check if user's preferred days threshold matches this check
        user_expiry_days = get_subscription_expiry_days(user)
        if days > user_expiry_days:
            return False

        # Use user.id + subscription.id for key to support multiple subscriptions per user
        sub_key = f'user_{user.id}_sub_{subscription.id}_today'
        user_identifier = user.telegram_id or f'email:{user.id}'

        if (user.id, subscription.id, days) in already_sent or sub_key in processed:
            logger.debug(
                'Уведомление уже отправлено, пропускаем',
                user_identifier=user_identifier,
                days=days,
            )
            return False

        for other_days in warning_days:
            if other_days < days and subscription.id in urgent_ids_by_days[other_days]:
                logger.debug(
                    '🎯 Пропускаем уведомление на дней для пользователя есть более срочное на дней',
                    days=days,
                    user_identifier=user_identifier,
                    other_days=other_days,
                )
                return False

        if subscription.autopay_enabled and await self._is_marked(autopay_fail_notice_key(subscription.id)):
            # В эти сутки уже ушло «Автопродление не прошло» — там сумма и кнопка пополнения.
            # Этот порог считаем закрытым, чтобы напоминание не догнало человека следующим циклом.
            await record_notification(db, user.id, subscription.id, 'expiring', days)
            already_sent.add((user.id, subscription.id, days))
            processed.add(sub_key)
            logger.info(
                'Напоминание об истечении не шлём: в эти сутки ушло «Автопродление не прошло»',
                user_id=user.id,
                subscription_id=subscription.id,
                days=days,
            )
            return False

        # Handle email-only users via notification delivery service
        if not user.telegram_id:
            success = await notification_delivery_service.notify_subscription_expiring(
                user=user,
                days_left=days,
                expires_at=subscription.end_date,
            )
            if not success:
                return False
            await record_notification(db, user.id, subscription.id, 'expiring', days)
            already_sent.add((user.id, subscription.id, days))
            processed.add(sub_key)
            logger.info(
                '✅ Email-пользователю отправлено уведомление об истечении подписки через дней',
                user_id=user.id,
                days=days,
            )
            return True

        if not self.bot:
            return False

        renewal_price = (
            await self._autopay_renewal_price(db, user, subscription) if subscription.autopay_enabled else None
        )
        # Цену передаём, только когда она посчитана: без неё напоминание работает по-прежнему.
        price_kwargs = {'renewal_price': renewal_price} if renewal_price is not None else {}
        success = await self._send_subscription_expiring_notification(user, subscription, days, **price_kwargs)
        if not success:
            logger.warning('❌ Не удалось отправить уведомление пользователю', telegram_id=user.telegram_id)
            return False
        await record_notification(db, user.id, subscription.id, 'expiring', days)
        already_sent.add((user.id, subscription.id, days))
        processed.add(sub_key)
        logger.info(
            '✅ Пользователю отправлено уведомление об истечении подписки через дней',
            telegram_id=user.telegram_id,
            days=days,
        )
        return True

    async def _run_activation_funnel(self, db: AsyncSession):
        try:
            from app.services.activation_funnel_service import ActivationFunnelService

            funnel = ActivationFunnelService(bot=self.bot, send_func=self._send_message_with_logo)
            await funnel.process(db)
        except Exception as error:
            logger.error('Ошибка activation funnel', error=error, exc_info=True)
            await _rollback_quietly(db, step='activation_funnel')

    async def _check_trial_expiring_soon(self, db: AsyncSession):
        if not NotificationSettingsService.are_notifications_globally_enabled():
            return

        try:
            threshold_time = datetime.now(UTC) + timedelta(hours=2)

            result = await db.execute(
                select(Subscription)
                .join(Subscription.user)
                .options(
                    selectinload(Subscription.tariff),
                    selectinload(Subscription.user).selectinload(User.promo_group),
                    selectinload(Subscription.user)
                    .selectinload(User.user_promo_groups)
                    .selectinload(UserPromoGroup.promo_group),
                )
                .where(
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE.value,
                        Subscription.is_trial == True,
                        Subscription.end_date <= threshold_time,
                        Subscription.end_date > datetime.now(UTC),
                        User.status == UserStatus.ACTIVE.value,
                    )
                )
            )
            trial_expiring = result.scalars().all()

            for subscription in trial_expiring:
                user = subscription.user
                if not user:
                    continue

                from app.utils.notification_prefs import is_subscription_expiry_enabled

                if not is_subscription_expiry_enabled(user):
                    continue

                if await notification_sent(db, user.id, subscription.id, 'trial_2h'):
                    continue

                if self.bot:
                    success = await self._send_trial_ending_notification(user, subscription)
                    if success:
                        await record_notification(db, user.id, subscription.id, 'trial_2h')
                        logger.info(
                            '🎁 Пользователю отправлено уведомление об окончании тестовой подписки через 2 часа',
                            telegram_id=user.telegram_id,
                        )

            if trial_expiring:
                await self._log_monitoring_event(
                    db,
                    'trial_expiring_notifications_sent',
                    f'Отправлено {len(trial_expiring)} уведомлений об окончании тестовых подписок',
                    {'count': len(trial_expiring)},
                )

        except Exception as e:
            logger.error('Ошибка проверки истекающих тестовых подписок', error=e)
            await _rollback_quietly(db, step='trial_expiring_soon')

    async def _check_trial_channel_subscriptions(self, db: AsyncSession):
        """Background reconciliation of channel subscriptions (rate-limited).

        Processes subscriptions in batches using keyset pagination to avoid
        loading all trial subscriptions into memory at once. Each batch gets
        a fresh DB session to avoid holding a connection pool slot for hours.

        When CHANNEL_REQUIRED_FOR_ALL is True, checks ALL active subscriptions
        (not just trials). Otherwise only checks trial subscriptions.
        """
        from app.database.crud.subscription import is_recently_updated_by_webhook

        if not settings.CHANNEL_IS_REQUIRED_SUB:
            return

        if not self.bot:
            logger.debug('Skipping channel subscription check - bot unavailable')
            return

        from app.database.crud.required_channel import upsert_user_channel_sub
        from app.services.channel_subscription_service import channel_subscription_service
        from app.utils.cache import ChannelSubCache

        channels = await channel_subscription_service.get_required_channels()
        if not channels:
            return

        # When no channel has any disable-on-leave rule, skip deactivation but
        # still run reactivation to restore orphaned DISABLED subscriptions
        # (e.g., admin turned off disable flags after subscriptions were already disabled).
        has_any_disable_rule = any(
            ch.get('disable_trial_on_leave', True) or ch.get('disable_paid_on_leave', False) for ch in channels
        )
        skip_deactivation = not has_any_disable_rule and not settings.CHANNEL_REQUIRED_FOR_ALL

        # Ensure bot is set on service
        if not channel_subscription_service.bot:
            channel_subscription_service.bot = self.bot

        try:
            now = datetime.now(UTC)
            notifications_allowed = (
                NotificationSettingsService.are_notifications_globally_enabled()
                and NotificationSettingsService.is_trial_channel_unsubscribed_enabled()
            )

            disabled_count = 0
            restored_count = 0
            checked_count = 0
            last_id = 0

            # Build the trial/all filter based on CHANNEL_REQUIRED_FOR_ALL setting
            # Also include paid subs if any channel has disable_paid_on_leave=True,
            # so monitoring can reconcile missed real-time events for paid users.
            from sqlalchemy import true as sa_true

            has_paid_disable_rule = any(ch.get('disable_paid_on_leave', False) for ch in channels)
            include_all = settings.CHANNEL_REQUIRED_FOR_ALL or has_paid_disable_rule
            is_trial_filter = sa_true() if include_all else Subscription.is_trial.is_(True)

            while True:
                # Fresh session per batch to avoid long-running connections
                async with AsyncSessionLocal() as batch_db:
                    result = await batch_db.execute(
                        select(Subscription)
                        .join(Subscription.user)
                        .options(
                            selectinload(Subscription.user),
                            selectinload(Subscription.tariff),
                        )
                        .where(
                            and_(
                                Subscription.id > last_id,
                                is_trial_filter,
                                Subscription.end_date > now,
                                Subscription.status.in_(
                                    [
                                        SubscriptionStatus.ACTIVE.value,
                                        SubscriptionStatus.DISABLED.value,
                                    ]
                                ),
                                User.status == UserStatus.ACTIVE.value,
                            )
                        )
                        .order_by(Subscription.id)
                        .limit(_CHANNEL_CHECK_BATCH_SIZE)
                    )

                    subscriptions = result.scalars().all()
                    if not subscriptions:
                        break

                    last_id = subscriptions[-1].id

                    for subscription in subscriptions:
                        user = subscription.user
                        if not user or not user.telegram_id:
                            continue

                        # Skip admins -- consistent with channel_member.py and channel_checker.py
                        if settings.is_admin(user.telegram_id):
                            continue

                        # Existing guard: skip if recently updated by webhook
                        if is_recently_updated_by_webhook(subscription):
                            logger.debug(
                                'Skipping subscription: recently updated by webhook',
                                subscription_id=subscription.id,
                            )
                            continue

                        checked_count += 1

                        # Rate-limited check for ALL channels.
                        # _rate_limited_check returns Optional[bool] — None means
                        # "could not determine" (network blip, double rate-limit,
                        # generic exception). Treat None as "keep the last known
                        # value" and never feed it into the deactivation path —
                        # closes the same regression #313502 covered for the
                        # request-time middleware. This background reconciler
                        # would otherwise still flip annual paid subs to DISABLED
                        # on the very next monitoring tick after a transient
                        # Telegram API hiccup.
                        all_subscribed = True
                        unsubscribed_channels: list[dict] = []
                        for ch in channels:
                            check_result = await channel_subscription_service._rate_limited_check(
                                user.telegram_id, ch['channel_id']
                            )
                            if check_result is None:
                                # Skip DB/cache writes and don't mark as unsubscribed —
                                # the next reconciler tick (or the next user
                                # interaction in the request path) will retry.
                                continue
                            is_member = check_result
                            # Update DB + cache only when we have a definitive answer
                            await upsert_user_channel_sub(batch_db, user.telegram_id, ch['channel_id'], is_member)
                            await ChannelSubCache.set_sub_status(user.telegram_id, ch['channel_id'], is_member)

                            if not is_member:
                                all_subscribed = False
                                unsubscribed_channels.append(ch)

                        # DEACTIVATE: was active, now not subscribed to all
                        if subscription.status == SubscriptionStatus.ACTIVE.value and not all_subscribed:
                            if skip_deactivation:
                                continue

                            # Respect per-channel disable_trial_on_leave / disable_paid_on_leave settings
                            should_disable = any(
                                channel_subscription_service.should_disable_subscription(ch, subscription.is_trial)
                                for ch in unsubscribed_channels
                            )
                            if not should_disable:
                                continue

                            subscription = await deactivate_subscription(batch_db, subscription, commit=False)
                            disabled_count += 1
                            logger.info(
                                'Subscription deactivated (channel unsubscribe)',
                                telegram_id=user.telegram_id,
                                subscription_id=subscription.id,
                                is_trial=subscription.is_trial,
                            )

                            panel_user_id = user.remnawave_id
                            if panel_user_id is not None:
                                try:
                                    await self.subscription_service.disable_remnawave_user(panel_user_id)
                                except Exception as api_error:
                                    logger.error(
                                        'Failed to disable RemnaWave user',
                                        remnawave_id=panel_user_id,
                                        api_error=api_error,
                                    )

                            if notifications_allowed:
                                if not await notification_sent(
                                    batch_db,
                                    user.id,
                                    subscription.id,
                                    'trial_channel_unsubscribed',
                                ):
                                    sent = await self._send_trial_channel_unsubscribed_notification(user)
                                    if sent:
                                        await record_notification(
                                            batch_db,
                                            user.id,
                                            subscription.id,
                                            'trial_channel_unsubscribed',
                                            commit=False,
                                        )

                        # REACTIVATE: was disabled, now subscribed to all
                        elif subscription.status == SubscriptionStatus.DISABLED.value and all_subscribed:
                            # Guard: traffic limit exhausted
                            if (
                                subscription.traffic_limit_gb
                                and subscription.traffic_used_gb is not None
                                and subscription.traffic_used_gb >= subscription.traffic_limit_gb
                            ):
                                logger.debug(
                                    'Skipping reactivation: traffic exhausted',
                                    subscription_id=subscription.id,
                                    traffic_used=subscription.traffic_used_gb,
                                    traffic_limit=subscription.traffic_limit_gb,
                                )
                                continue

                            # Guard: disabled by webhook, not by monitoring
                            if (
                                subscription.last_webhook_update_at
                                and subscription.updated_at
                                and subscription.last_webhook_update_at
                                >= subscription.updated_at - timedelta(seconds=10)
                            ):
                                logger.debug(
                                    'Skipping reactivation: disabled by RemnaWave panel',
                                    subscription_id=subscription.id,
                                    last_webhook_at=subscription.last_webhook_update_at,
                                    updated_at=subscription.updated_at,
                                )
                                continue

                            subscription = await reactivate_subscription(batch_db, subscription, commit=False)
                            if subscription.status != SubscriptionStatus.ACTIVE.value:
                                # reactivate_subscription silently skipped (expired or wrong status)
                                continue

                            restored_count += 1
                            logger.info(
                                'Subscription restored (channel resubscribe)',
                                telegram_id=user.telegram_id,
                                subscription_id=subscription.id,
                                is_trial=subscription.is_trial,
                            )

                            try:
                                _should_create = getattr(user, 'remnawave_id', None) is None

                                if _should_create:
                                    # create_remnawave_user calls db.commit() internally --
                                    # flush accumulated batch state first to preserve atomicity.
                                    await batch_db.commit()
                                    await self.subscription_service.create_remnawave_user(batch_db, subscription)
                                else:
                                    _enable_panel_user_id = user.remnawave_id
                                    if _enable_panel_user_id is not None:
                                        await self.subscription_service.enable_remnawave_user(_enable_panel_user_id)
                            except Exception as api_error:
                                logger.error(
                                    'Failed to update RemnaWave user',
                                    telegram_id=user.telegram_id,
                                    api_error=api_error,
                                )

                            await clear_notification_by_type(
                                batch_db,
                                subscription.id,
                                'trial_channel_unsubscribed',
                                commit=False,
                            )

                    # Commit all changes for this batch
                    await batch_db.commit()

            if disabled_count or restored_count:
                check_scope = 'all' if settings.CHANNEL_REQUIRED_FOR_ALL else 'trial'
                await self._log_monitoring_event(
                    db,
                    'trial_channel_subscription_check',
                    (
                        f'Checked {checked_count} {check_scope} subscriptions: '
                        f'disabled {disabled_count}, restored {restored_count}'
                    ),
                    {
                        'checked': checked_count,
                        'disabled': disabled_count,
                        'restored': restored_count,
                        'scope': check_scope,
                    },
                )

        except Exception as error:
            logger.error('Error checking channel subscriptions', error=error)
            await _rollback_quietly(db, step='trial_channel_subscriptions')

    async def _check_expired_subscription_followups(self, db: AsyncSession):
        if not NotificationSettingsService.are_notifications_globally_enabled():
            return
        if not self.bot:
            return
        # Переключатели читаются живьём из settings (база), не из файла: выключили — этот цикл уже видит.
        if not (
            NotificationSettingsService.is_expired_1d_enabled()
            or NotificationSettingsService.is_second_wave_enabled()
            or NotificationSettingsService.is_third_wave_enabled()
        ):
            return

        try:
            now = datetime.now(UTC)

            # Догоняющие письма после окончания не срочные — ночью не будим. Окна у
            # них 24–48 ч, тихие часы короче, так что письмо уйдёт днём того же окна.
            from app.utils.quiet_hours import is_quiet_time
            from app.utils.timezone import get_local_timezone

            if is_quiet_time(
                now,
                start_hour=settings.USER_REMINDERS_QUIET_HOURS_START,
                end_hour=settings.USER_REMINDERS_QUIET_HOURS_END,
                tz=get_local_timezone(),
            ):
                return

            # Lookback window — don't re-check subscriptions expired more than 30 days ago
            lookback = now - timedelta(days=30)

            result = await db.execute(
                select(Subscription)
                .join(User, Subscription.user_id == User.id)
                .options(
                    selectinload(Subscription.user)
                    .selectinload(User.user_promo_groups)
                    .selectinload(UserPromoGroup.promo_group),
                    selectinload(Subscription.user).selectinload(User.promo_group),
                    selectinload(Subscription.tariff),
                )
                .where(
                    and_(
                        Subscription.is_trial == False,
                        Subscription.status == SubscriptionStatus.EXPIRED.value,
                        Subscription.end_date <= now,
                        Subscription.end_date >= lookback,
                        User.status == UserStatus.ACTIVE.value,
                    )
                )
            )

            all_subscriptions = result.scalars().all()

            # Исключаем суточные тарифы - для них отдельная логика
            subscriptions = [
                sub for sub in all_subscriptions if not (sub.tariff and getattr(sub.tariff, 'is_daily', False))
            ]

            sent_day1 = 0
            sent_wave2 = 0
            sent_wave3 = 0

            for subscription in subscriptions:
                user = subscription.user
                if not user:
                    continue

                from app.utils.notification_prefs import is_subscription_expiry_enabled

                if not is_subscription_expiry_enabled(user):
                    continue

                if subscription.end_date is None:
                    continue

                time_since_end = now - subscription.end_date
                if time_since_end.total_seconds() < 0:
                    continue

                days_since = time_since_end.total_seconds() / 86400

                # Day 1 reminder
                if NotificationSettingsService.is_expired_1d_enabled() and 1 <= days_since < 2:
                    if not await notification_sent(db, user.id, subscription.id, 'expired_1d'):
                        success = await self._send_expired_day1_notification(db, user, subscription)
                        if success:
                            await record_notification(db, user.id, subscription.id, 'expired_1d')
                            sent_day1 += 1

                # Second wave (2-3 days) discount
                if NotificationSettingsService.is_second_wave_enabled() and 2 <= days_since < 4:
                    if not await notification_sent(db, user.id, subscription.id, 'expired_discount_wave2'):
                        percent = NotificationSettingsService.get_second_wave_discount_percent()
                        valid_hours = NotificationSettingsService.get_second_wave_valid_hours()
                        offer = await upsert_discount_offer(
                            db,
                            user_id=user.id,
                            subscription_id=subscription.id,
                            notification_type='expired_discount_wave2',
                            discount_percent=percent,
                            bonus_amount_kopeks=0,
                            valid_hours=valid_hours,
                            effect_type='percent_discount',
                        )
                        success = await self._send_expired_discount_notification(
                            user,
                            subscription,
                            percent,
                            offer.expires_at,
                            offer.id,
                            'second',
                        )
                        if success:
                            await record_notification(db, user.id, subscription.id, 'expired_discount_wave2')
                            sent_wave2 += 1

                # Third wave (N days) discount
                if NotificationSettingsService.is_third_wave_enabled():
                    trigger_days = NotificationSettingsService.get_third_wave_trigger_days()
                    if trigger_days <= days_since < trigger_days + 1:
                        if not await notification_sent(db, user.id, subscription.id, 'expired_discount_wave3'):
                            percent = NotificationSettingsService.get_third_wave_discount_percent()
                            valid_hours = NotificationSettingsService.get_third_wave_valid_hours()
                            offer = await upsert_discount_offer(
                                db,
                                user_id=user.id,
                                subscription_id=subscription.id,
                                notification_type='expired_discount_wave3',
                                discount_percent=percent,
                                bonus_amount_kopeks=0,
                                valid_hours=valid_hours,
                                effect_type='percent_discount',
                            )
                            success = await self._send_expired_discount_notification(
                                user,
                                subscription,
                                percent,
                                offer.expires_at,
                                offer.id,
                                'third',
                                trigger_days=trigger_days,
                            )
                            if success:
                                await record_notification(db, user.id, subscription.id, 'expired_discount_wave3')
                                sent_wave3 += 1

            if sent_day1 or sent_wave2 or sent_wave3:
                await self._log_monitoring_event(
                    db,
                    'expired_followups_sent',
                    (f'Follow-ups: 1д={sent_day1}, скидка 2-3д={sent_wave2}, скидка N={sent_wave3}'),
                    {
                        'day1': sent_day1,
                        'wave2': sent_wave2,
                        'wave3': sent_wave3,
                    },
                )

        except Exception as e:
            logger.error('Ошибка проверки напоминаний об истекшей подписке', error=e)
            await _rollback_quietly(db, step='expired_followups')

    async def _get_expiring_paid_subscriptions(self, db: AsyncSession, days_before: int) -> list[Subscription]:
        current_time = datetime.now(UTC)
        threshold_date = current_time + timedelta(days=days_before)

        result = await db.execute(
            select(Subscription)
            .join(User, Subscription.user_id == User.id)
            .options(
                # Пользователь и его группы — сразу пачкой: напоминания о сроке
                # не делают отдельных запросов на каждую подписку.
                selectinload(Subscription.user).selectinload(User.promo_group),
                selectinload(Subscription.user)
                .selectinload(User.user_promo_groups)
                .selectinload(UserPromoGroup.promo_group),
                selectinload(Subscription.tariff),
            )
            .where(
                and_(
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    Subscription.is_trial == False,
                    Subscription.end_date > current_time,
                    Subscription.end_date <= threshold_date,
                    User.status == UserStatus.ACTIVE.value,
                )
            )
        )

        logger.debug('🔍 Поиск платных подписок, истекающих в ближайшие дней', days_before=days_before)
        logger.debug('📅 Текущее время', current_time=current_time)
        logger.debug('📅 Пороговая дата', threshold_date=threshold_date)

        all_subscriptions = result.scalars().all()

        # Исключаем суточные тарифы - для них отдельная логика списания
        subscriptions = [
            sub for sub in all_subscriptions if not (sub.tariff and getattr(sub.tariff, 'is_daily', False))
        ]

        excluded_count = len(all_subscriptions) - len(subscriptions)
        if excluded_count > 0:
            logger.debug('🔄 Исключено суточных подписок из уведомлений', excluded_count=excluded_count)

        logger.info('📊 Найдено платных подписок для уведомлений', subscriptions_count=len(subscriptions))

        return subscriptions

    async def _process_autopayments(self, db: AsyncSession):
        try:
            current_time = datetime.now(UTC)

            # Берём ACTIVE + недавно EXPIRED (middleware или check_and_update могли
            # экспайрить до того, как monitoring успел запустить autopay)
            recently_expired_threshold = current_time - timedelta(hours=2)
            result = await db.execute(
                select(Subscription)
                .options(
                    selectinload(Subscription.user).options(
                        selectinload(User.promo_group),
                        selectinload(User.user_promo_groups).selectinload(UserPromoGroup.promo_group),
                    ),
                    selectinload(Subscription.tariff),
                )
                .where(
                    and_(
                        or_(
                            Subscription.status == SubscriptionStatus.ACTIVE.value,
                            # Подписки, которые были экспайрены middleware/CRUD
                            # недавно (в пределах 2ч) — autopay может их восстановить
                            and_(
                                Subscription.status == SubscriptionStatus.EXPIRED.value,
                                Subscription.end_date >= recently_expired_threshold,
                            ),
                        ),
                        Subscription.autopay_enabled == True,
                        Subscription.is_trial == False,
                    )
                )
            )
            all_autopay_subscriptions = result.scalars().all()

            autopay_subscriptions = []
            for sub in all_autopay_subscriptions:
                # Суточные подписки имеют свой собственный механизм продления
                # (DailySubscriptionService), глобальный autopay на них не распространяется
                if sub.tariff and getattr(sub.tariff, 'is_daily', False):
                    logger.debug(
                        'Пропускаем суточную подписку (тариф) в глобальном autopay', sub_id=sub.id, name=sub.tariff.name
                    )
                    continue

                # Skip classic subscriptions (tariff_id=NULL) when tariff mode is active
                if not sub.tariff_id:
                    logger.debug(
                        'Пропускаем классическую подписку без тарифа в autopay (tariff mode)',
                        sub_id=sub.id,
                        user_id=sub.user_id,
                    )
                    # Notify user once that autopay won't work without a tariff
                    autopay_legacy_key = f'autopay_legacy_notified:{sub.user_id}'
                    try:
                        if not await cache.exists(autopay_legacy_key):
                            user = sub.user
                            if (
                                user
                                and user.telegram_id
                                and self.bot
                                and NotificationSettingsService.are_notifications_globally_enabled()
                            ):
                                await self.bot.send_message(
                                    chat_id=user.telegram_id,
                                    text=(
                                        '⚠️ <b>Автопродление приостановлено</b>\n\n'
                                        'Подписка оформлена до введения тарифов. '
                                        'Выберите тариф, и автопродление снова заработает.'
                                    ),
                                    reply_markup=keyboard(buy_button(get_texts(user.language))),
                                    parse_mode='HTML',
                                )
                            await cache.set(autopay_legacy_key, 1, expire=86400 * 7)
                    except Exception as notify_err:
                        logger.debug('Не удалось уведомить о пропуске autopay для legacy подписки', error=notify_err)
                    continue

                if ends_within_days(sub.end_date, min(sub.autopay_days_before or 3, 3), current_time):
                    autopay_subscriptions.append(sub)

            processed_count = 0
            failed_count = 0

            # Захватываем (sub_id, user_id) ДО цикла, пока сессия ещё свежая.
            # В цикле каждую итерацию делаем refetch subscription+user через
            # async-запрос: это единственный безопасный способ избежать
            # MissingGreenlet при sync-lazy-load, который SQLAlchemy 2.0 async
            # session не поддерживает (напр. lock_user_for_pricing c
            # populate_existing=True разгружает Subscription.user backref).
            autopay_pairs = [(s.id, s.user_id, s.end_date) for s in autopay_subscriptions]

            for sub_id_local, sub_user_id_local, expected_end_date in autopay_pairs:
                try:
                    lock = await lock_autopay_target_checked(
                        db, sub_user_id_local, sub_id_local, expected_end_date=expected_end_date
                    )
                    if lock.skip_reason is not None:
                        if lock.skip_reason == 'tariff_inactive':
                            # Тариф отключён — списание не пройдёт никогда, а напоминание
                            # обещало «ничего делать не нужно». Говорим прямо (разово).
                            await self._notify_autopay_cannot_renew(
                                lock.user, lock.subscription, cause='tariff_inactive'
                            )
                        continue
                    user, subscription = lock.user, lock.subscription

                    from app.database.crud.subscription import is_recently_updated_by_webhook

                    if is_recently_updated_by_webhook(subscription):
                        logger.debug(
                            'Пропуск автоплатежа подписки : обновлена вебхуком недавно',
                            subscription_id=subscription.id,
                        )
                        continue

                    user_identifier = user.telegram_id or f'email:{user.id}'

                    # Период продления выбирается с такой иерархией:
                    #   1. subscription.autopay_period_days — выбор пользователя/админа
                    #   2. settings.DEFAULT_AUTOPAY_PERIOD_DAYS — глобальный дефолт из .env
                    #   3. tariff.get_shortest_period() — самый дешёвый период тарифа (legacy)
                    #   4. 30 — финальный fallback, если тарифа нет
                    # resolve_autopay_period_candidate работает fail-closed: пропускает только
                    # значения из tariff.get_available_periods() или (для классических подписок
                    # без тарифа) settings.get_available_renewal_periods().
                    tariff = getattr(subscription, 'tariff', None)

                    autopay_period = (
                        resolve_autopay_period_candidate(getattr(subscription, 'autopay_period_days', None), tariff)
                        or resolve_autopay_period_candidate(settings.DEFAULT_AUTOPAY_PERIOD_DAYS, tariff)
                        or (tariff.get_shortest_period() if tariff else None)
                        or 30
                    )

                    try:
                        from app.services.pricing_engine import pricing_engine

                        pricing = await pricing_engine.calculate_renewal_price(
                            db,
                            subscription,
                            autopay_period,
                            user=user,
                        )
                        renewal_cost = pricing.final_total
                    except Exception as e:
                        logger.error(
                            'Ошибка расчёта стоимости автопродления, пропускаем',
                            subscription_id=subscription.id,
                            user_id=user.id,
                            error=str(e),
                        )
                        failed_count += 1
                        # Уведомление не ходит в БД; объекты ещё загружены (rollback
                        # ниже их экспайрит), а блокировки снимет этот же rollback.
                        await self._notify_autopay_cannot_renew(user, subscription, cause='price_error')
                        await db.rollback()
                        continue

                    # Ноль сам по себе не повод отказать: бесплатный период —
                    # штатная настройка тарифа, и подписку на нём покупают как
                    # любую другую. Отказ остаётся для случая, ради которого
                    # проверка и появилась, — цена периода не проставлена вовсе.
                    autopay_period_is_priced = bool(tariff and tariff.has_configured_price_for_period(autopay_period))
                    if renewal_cost <= 0 and not autopay_period_is_priced:
                        logger.warning(
                            'Нулевая стоимость автопродления, пропускаем',
                            subscription_id=subscription.id,
                            user_id=user.id,
                            renewal_cost=renewal_cost,
                        )
                        failed_count += 1
                        await self._notify_autopay_cannot_renew(user, subscription, cause='period_unpriced')
                        continue

                    # calculate_renewal_price уже включает promo_group + promo_offer скидки.
                    # Не применяем promo_offer повторно — только consume-им при успешной оплате.
                    charge_amount = renewal_cost
                    promo_discount_percent = get_user_active_promo_discount_percent(
                        user, getattr(subscription, 'tariff_id', None)
                    )

                    autopay_key = f'autopay_{user.id}_{subscription.id}'
                    if autopay_key in self._notified_users:
                        continue

                    if user.balance_kopeks >= charge_amount:
                        success = await subtract_user_balance(
                            db,
                            user,
                            charge_amount,
                            'Автопродление подписки',
                            consume_promo_offer=promo_discount_percent > 0,
                            mark_as_paid_subscription=True,
                            commit=False,
                        )

                        if success:
                            from app.database.crud.transaction import create_transaction, emit_transaction_side_effects
                            from app.database.models import PaymentMethod, TransactionType

                            old_end_date = subscription.end_date
                            await extend_subscription(db, subscription, autopay_period, commit=False)
                            description = f'Автопродление подписки на {autopay_period} дней'
                            transaction = await create_transaction(
                                db=db,
                                user_id=user.id,
                                type=TransactionType.SUBSCRIPTION_PAYMENT,
                                amount_kopeks=charge_amount,
                                description=description,
                                payment_method=PaymentMethod.BALANCE,
                                commit=False,
                            )
                            # Debit, expiry and ledger become durable together. No
                            # other worker can charge this due cycle in between.
                            await db.commit()
                            await emit_transaction_side_effects(
                                db,
                                transaction,
                                amount_kopeks=charge_amount,
                                user_id=sub_user_id_local,
                                type=TransactionType.SUBSCRIPTION_PAYMENT,
                                payment_method=PaymentMethod.BALANCE,
                                description=description,
                            )

                            await db.refresh(user)
                            await db.refresh(subscription)
                            try:
                                result = await self.subscription_service.update_remnawave_user(
                                    db,
                                    subscription,
                                    reset_traffic=settings.RESET_TRAFFIC_ON_PAYMENT,
                                    reset_reason='автопродление подписки',
                                )
                            except Exception as sync_exc:
                                result = None
                                logger.error(
                                    'Autopay panel sync failed after commit',
                                    subscription_id=sub_id_local,
                                    error=sync_exc,
                                )
                            # Panel service may rollback and expire ORM even when
                            # returning None. Money and ledger were committed above.
                            await db.refresh(user)
                            await db.refresh(subscription)
                            await db.refresh(transaction)
                            if result is None:
                                from app.services.remnawave_retry_queue import remnawave_retry_queue

                                remnawave_retry_queue.enqueue(
                                    subscription_id=sub_id_local,
                                    user_id=sub_user_id_local,
                                    action='update',
                                    reset_traffic=settings.RESET_TRAFFIC_ON_PAYMENT,
                                    reset_reason='автопродление подписки',
                                )

                            # Отправляем уведомление администраторам
                            try:
                                from app.services.subscription_renewal_service import with_admin_notification_service

                                if transaction:
                                    await with_admin_notification_service(
                                        lambda svc: svc.send_subscription_extension_notification(
                                            db,
                                            user,
                                            subscription,
                                            transaction,
                                            autopay_period,
                                            old_end_date,
                                            new_end_date=subscription.end_date,
                                            balance_after=user.balance_kopeks,
                                        )
                                    )
                            except Exception as exc:
                                logger.warning(
                                    'Не удалось отправить админ-уведомление об автопродлении', user_id=user.id, exc=exc
                                )

                            # Send notification via appropriate channel
                            if (
                                user.telegram_id
                                and self.bot
                                and NotificationSettingsService.are_notifications_globally_enabled()
                            ):
                                await self._send_autopay_success_notification(user, charge_amount, autopay_period)
                            elif not user.telegram_id:
                                # Email-only user - use notification delivery service
                                await notification_delivery_service.notify_autopay_success(
                                    user=user,
                                    amount_kopeks=charge_amount,
                                    new_expires_at=subscription.end_date,
                                )

                            processed_count += 1
                            self._notified_users.add(autopay_key)
                            logger.info(
                                '💳 Автопродление подписки прошло успешно',
                                user_identifier=user_identifier,
                                charge_amount=charge_amount,
                                promo_discount_percent=promo_discount_percent,
                            )
                        else:
                            failed_count += 1
                            await self._maybe_notify_autopay_failure(
                                user, charge_amount, subscription, current_time, cause='charge_error'
                            )
                            logger.warning(
                                '💳 Ошибка списания средств для автопродления пользователя',
                                user_identifier=user_identifier,
                            )
                    else:
                        failed_count += 1
                        await self._maybe_notify_autopay_failure(user, charge_amount, subscription, current_time)
                        logger.warning(
                            '💳 Недостаточно средств для автопродления у пользователя',
                            user_identifier=user_identifier,
                        )
                except Exception as sub_error:
                    failed_count += 1
                    # Используем локально захваченные id — subscription-объект
                    # может быть expired после чужого rollback'а.
                    logger.error(
                        'Ошибка автопродления отдельной подписки',
                        subscription_id=sub_id_local,
                        user_id=sub_user_id_local,
                        error=sub_error,
                        exc_info=True,
                    )
                    # Сессия могла остаться с aborted-транзакцией — откатываем,
                    # чтобы следующая итерация начала refetch на чистой сессии.
                    try:
                        await db.rollback()
                    except Exception as rollback_error:
                        logger.warning(
                            'Не удалось сделать rollback сессии после ошибки автопродления',
                            rollback_error=rollback_error,
                        )
                    continue
                finally:
                    # Also release locks on eligibility/price/balance early exits.
                    await db.rollback()

            if processed_count > 0 or failed_count > 0:
                await self._log_monitoring_event(
                    db,
                    'autopayments_processed',
                    f'Автоплатежи: успешно {processed_count}, неудачно {failed_count}',
                    {'processed': processed_count, 'failed': failed_count},
                )

        except Exception as e:
            logger.error('Ошибка обработки автоплатежей', error=e, exc_info=True)
            await _rollback_quietly(db, step='autopayments')

    async def _send_subscription_expired_notification(
        self, user: User, subscription: Subscription, *, tariff_name: str | None = None
    ) -> bool:
        try:
            if not user.telegram_id:
                return await notification_delivery_service.send_notification(
                    user=user,
                    notification_type=NotificationType.SUBSCRIPTION_EXPIRED,
                    context={'tariff_name': tariff_name or ''},
                )
            tariff_label = ''
            texts = get_texts(user.language)
            from aiogram.types import InlineKeyboardMarkup

            if getattr(subscription, 'is_trial', False):
                # Кончился пробный период — продлевать нечего: «Продлите подписку» и «Пополнить
                # баланс» тут не про то. Одно предложение — оформить подписку.
                message = texts.t(
                    'TRIAL_EXPIRED_NOTICE',
                    '⏳ <b>Пробный период закончился</b>\n\nОформите подписку — VPN заработает сразу.',
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            build_miniapp_or_callback_button(
                                text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy', style='success'
                            )
                        ],
                    ]
                )
            else:
                # Текст из локалей (был зашит по-русски и не переводился).
                message = texts.t(
                    'SUBSCRIPTION_EXPIRED',
                    '🔴 <b>Подписка{tariff_label} закончилась</b>\n\nПродлите, и VPN снова заработает.',
                ).format(tariff_label=tariff_label)
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            build_subscription_extend_button(
                                texts.t('MENU_EXTEND_SUBSCRIPTION', '⏰ Продлить подписку'),
                                style='success',
                            )
                        ],
                        [
                            build_miniapp_or_callback_button(
                                text=texts.t('BALANCE_TOPUP', '💳 Пополнить баланс'),
                                callback_data='balance_topup',
                                style='success',
                            )
                        ],
                    ]
                )

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'уведомление об истечении подписки'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке уведомления об истечении подписки пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
            return False
        except Exception as e:
            logger.error(
                'Ошибка отправки уведомления об истечении подписки пользователю', telegram_id=user.telegram_id, e=e
            )
            return False

    async def _autopay_renewal_price(self, db: AsyncSession, user: User, subscription: Subscription) -> int | None:
        """Сколько спишет автопродление: тот же срок и тот же расчёт, что в ``_process_autopayments``.

        Нужен напоминанию об истечении: цена срока из тарифа не учитывает докупленные
        устройства, и человек с балансом между «ценой тарифа» и реальной ценой получал
        «ничего делать не нужно», а списание потом не проходило.
        """
        tariff = getattr(subscription, 'tariff', None)
        period = (
            resolve_autopay_period_candidate(getattr(subscription, 'autopay_period_days', None), tariff)
            or resolve_autopay_period_candidate(settings.DEFAULT_AUTOPAY_PERIOD_DAYS, tariff)
            or (tariff.get_shortest_period() if tariff else None)
            or 30
        )
        try:
            from app.services.pricing_engine import pricing_engine

            pricing = await pricing_engine.calculate_renewal_price(db, subscription, period, user=user)
        except Exception as error:
            logger.warning(
                'Не удалось посчитать цену автопродления для напоминания, беру цену срока из тарифа',
                subscription_id=getattr(subscription, 'id', None),
                error=str(error),
            )
            return None
        total = getattr(pricing, 'final_total', None)
        return total if isinstance(total, int) and total > 0 else None

    async def _send_subscription_expiring_notification(
        self,
        user: User,
        subscription: Subscription,
        days: int,
        *,
        has_saved_card: bool = False,
        renewal_price: int | None = None,
    ) -> bool:
        try:
            from app.utils.formatters import format_days_declension

            texts = get_texts(user.language)
            days_text = format_days_declension(days, user.language)

            # Если автоплатёж включен, но баланса не хватит — говорим прямо, пока есть
            # время пополниться: постфактум (при отказе списания) люди узнают слишком
            # поздно. Цена — та, что спишет автопродление (renewal_price): с докупленными
            # устройствами и скидками. Цена срока из тарифа остаётся запасной: она ниже
            # реальной, когда есть доп. устройства, и давала ложное «ничего делать не нужно».
            low_balance_action = None
            base_price = None
            if subscription.autopay_enabled:
                base_price = renewal_price
                if base_price is None:
                    tariff_for_price = getattr(subscription, 'tariff', None)
                    prices = getattr(tariff_for_price, 'period_prices', None) or {}
                    if prices:
                        period_days = (
                            getattr(subscription, 'autopay_period_days', None)
                            or settings.DEFAULT_AUTOPAY_PERIOD_DAYS
                            or (tariff_for_price.get_shortest_period() if tariff_for_price else None)
                            or 30
                        )
                        base_price = prices.get(str(period_days)) or None
                if base_price and (user.balance_kopeks or 0) < base_price:
                    low_balance_action = texts.t(
                        'AUTOPAY_ACTION_LOW_BALANCE',
                        '⚠️ Для автопродления нужно {cost}, на балансе {balance}. '
                        'Пополните заранее — иначе подписка остановится.',
                    ).format(cost=texts.format_price(base_price), balance=texts.format_price(user.balance_kopeks))

            if subscription.autopay_enabled:
                autopay_status = texts.t(
                    'AUTOPAY_STATUS_NO_CARD',
                    '✅ Включен — подписка продлится автоматически',
                )
                action_text = low_balance_action or texts.t(
                    'AUTOPAY_ACTION_CHECK_BALANCE',
                    '💰 Убедитесь, что на балансе достаточно средств: {balance}',
                ).format(balance=texts.format_price(user.balance_kopeks))
            else:
                autopay_status = texts.t(
                    'AUTOPAY_STATUS_OFF',
                    '❌ Отключен — не забудьте продлить вручную!',
                )
                if settings.ENABLE_AUTOPAY:
                    action_text = texts.t(
                        'AUTOPAY_ACTION_ENABLE',
                        '💡 Включите автоплатеж или продлите подписку вручную',
                    )
                else:
                    action_text = texts.t(
                        'AUTOPAY_ACTION_RENEW',
                        '💡 Продлите подписку вручную',
                    )

            end_date = format_local_datetime(subscription.end_date, '%d.%m.%Y %H:%M')
            tariff_label = ''

            # Автопродление включено и денег хватает — это не «продлите», а «продлим сами». Кнопка
            # «Продлить подписку» в таком письме приводила ко второй оплате того же периода.
            autopay_covers = subscription.autopay_enabled and low_balance_action is None
            if autopay_covers:
                from aiogram.types import InlineKeyboardMarkup

                if base_price:
                    message = texts.t(
                        'AUTOPAY_WILL_RENEW_WITH_COST',
                        '🔔 <b>{end_date} продлим подписку{tariff_label} автоматически</b>\n\n'
                        'Спишем {cost} с баланса — ничего делать не нужно.',
                    ).format(end_date=end_date, tariff_label=tariff_label, cost=texts.format_price(base_price))
                else:
                    message = texts.t(
                        'AUTOPAY_WILL_RENEW',
                        '🔔 <b>{end_date} продлим подписку{tariff_label} автоматически</b>\n\nНичего делать не нужно.',
                    ).format(end_date=end_date, tariff_label=tariff_label)
                await self._send_message_with_logo(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                build_miniapp_or_callback_button(
                                    text=texts.MENU_SUBSCRIPTION, callback_data='menu_subscription'
                                )
                            ]
                        ]
                    ),
                )
                return True

            message = texts.t(
                'SUBSCRIPTION_EXPIRING_PAID',
                '\n⚠️ <b>Подписка{tariff_label} истекает через {days_text}!</b>\n\n'
                'Ваша платная подписка истекает {end_date}.\n\n'
                '💳 <b>Автоплатеж:</b> {autopay_status}\n\n'
                '{action_text}\n',
            ).format(
                # Кастомные/старые локали используют {days} вместо {days_text} —
                # передаём оба, иначе .format() падает с KeyError('days') (#2737).
                days=days,
                days_text=days_text,
                end_date=end_date,
                autopay_status=autopay_status,
                action_text=action_text,
                tariff_label=tariff_label,
            )

            from aiogram.types import InlineKeyboardMarkup

            sub_btn_text = texts.t('BTN_MY_SUBSCRIPTION', '📱 Моя подписка')
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        build_subscription_extend_button(
                            texts.t('BTN_RENEW_SUBSCRIPTION', '⏰ Продлить подписку'), style='success'
                        )
                    ],
                    [
                        build_miniapp_or_callback_button(
                            text=texts.t('BTN_TOPUP_BALANCE', '💳 Пополнить баланс'),
                            callback_data='balance_topup',
                            style='success',
                        )
                    ],
                    [build_miniapp_or_callback_button(text=sub_btn_text, callback_data='menu_subscription')],
                ]
            )

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'уведомление об истекающей подписке'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке уведомления об истечении подписки пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
            return False
        except TelegramNetworkError as e:
            logger.warning(
                'Таймаут отправки уведомления об истечении подписки пользователю', telegram_id=user.telegram_id, e=e
            )
            return False
        except Exception as e:
            logger.error(
                'Ошибка отправки уведомления об истечении подписки пользователю', telegram_id=user.telegram_id, e=e
            )
            return False

    async def _send_trial_ending_notification(self, user: User, subscription: Subscription) -> bool:
        try:
            if not user.telegram_id:
                return await notification_delivery_service.send_notification(
                    user=user,
                    notification_type=NotificationType.WINBACK_TRIAL_ENDING,
                    context={},
                )
            texts = get_texts(user.language)

            # Spofy: use the strong localized TRIAL_ENDING_SOON copy (was hardcoded)
            message = texts.get(
                'TRIAL_ENDING_SOON',
                (
                    '⏰ <b>Пробный период закончится через 2 часа</b>\n\n'
                    'Оформите подписку сейчас, и VPN продолжит работать.'
                ),
            )

            from aiogram.types import InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        build_miniapp_or_callback_button(
                            text='💎 Купить подписку', callback_data='menu_buy', style='success'
                        )
                    ],
                    [build_miniapp_or_callback_button(text='💰 Пополнить баланс', callback_data='balance_topup')],
                ]
            )

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
                user=user,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'уведомление о завершении тестовой подписки'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке уведомления о завершении тестовой подписки пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
            return False
        except TelegramNetworkError as e:
            logger.warning(
                'Таймаут отправки уведомления об окончании тестовой подписки пользователю',
                telegram_id=user.telegram_id,
                e=e,
            )
            return False
        except Exception as e:
            logger.error(
                'Ошибка отправки уведомления об окончании тестовой подписки пользователю',
                telegram_id=user.telegram_id,
                e=e,
            )
            return False

    async def _send_trial_channel_unsubscribed_notification(self, user: User) -> bool:
        try:
            texts = get_texts(user.language)
            template = texts.get(
                'TRIAL_CHANNEL_UNSUBSCRIBED',
                (
                    '🚫 <b>Доступ приостановлен</b>\n\n'
                    'Мы не нашли вашу подписку на наш канал, поэтому тестовая подписка отключена.\n\n'
                    'Подпишитесь на канал и нажмите «{check_button}», чтобы вернуть доступ.'
                ),
            )

            check_button = texts.t('CHANNEL_CHECK_BUTTON', '✅ Я подписался')
            message = template.format(check_button=check_button)

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            from app.services.channel_subscription_service import channel_subscription_service

            unsubscribed = await channel_subscription_service.get_unsubscribed_channels(user.telegram_id)

            buttons = []
            for ch in unsubscribed:
                link = ch.get('channel_link')
                if link:
                    title = ch.get('title') or texts.t('CHANNEL_SUBSCRIBE_BUTTON', '🔗 Подписаться')
                    buttons.append([InlineKeyboardButton(text=f'🔗 {title}', url=link)])
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=check_button,
                        callback_data='sub_channel_check',
                        style='success',
                    )
                ]
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
                user=user,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'уведомление об отписке от канала'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке уведомления об отписке от канала пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
            return False
        except TelegramNetworkError as error:
            logger.warning(
                'Таймаут отправки уведомления об отписке от канала пользователю',
                telegram_id=user.telegram_id,
                error=error,
            )
            return False
        except Exception as error:
            logger.error(
                'Ошибка отправки уведомления об отписке от канала пользователю',
                telegram_id=user.telegram_id,
                error=error,
            )
            return False

    async def _send_expired_day1_notification(self, db: AsyncSession, user: User, subscription: Subscription) -> bool:
        try:
            if not user.telegram_id:
                return await notification_delivery_service.send_notification(
                    user=user,
                    notification_type=NotificationType.WINBACK_EXPIRED_1D,
                    context={'end_date': format_local_datetime(subscription.end_date, '%d.%m.%Y %H:%M')},
                )
            texts = get_texts(user.language)
            tariff = getattr(subscription, 'tariff', None)
            tariff_label = ''

            renewal_period = (tariff.get_shortest_period() if tariff else None) or 30
            try:
                from app.services.pricing_engine import pricing_engine

                pricing = await pricing_engine.calculate_renewal_price(db, subscription, renewal_period, user=user)
                renewal_price_kopeks = pricing.final_total
            except Exception as price_error:
                logger.warning(
                    'Не удалось рассчитать цену продления для уведомления expired_1d, используем PRICE_30_DAYS',
                    subscription_id=subscription.id,
                    user_id=user.id,
                    error=str(price_error),
                )
                renewal_price_kopeks = settings.PRICE_30_DAYS

            template = texts.get(
                'SUBSCRIPTION_EXPIRED_1D',
                (
                    '⛔ <b>Подписка{tariff_label} закончилась</b>\n\n'
                    'Доступ был отключён {end_date}. Продлите подписку, чтобы вернуться в сервис.'
                ),
            )
            message = template.format(
                end_date=format_local_datetime(subscription.end_date, '%d.%m.%Y %H:%M'),
                price=settings.format_price(renewal_price_kopeks),
                tariff_label=tariff_label,
            )

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        build_subscription_extend_button(
                            texts.t('SUBSCRIPTION_EXTEND', '💎 Продлить подписку'), style='success'
                        )
                    ],
                    [
                        build_miniapp_or_callback_button(
                            text=texts.t('BALANCE_TOPUP', '💳 Пополнить баланс'),
                            callback_data='balance_topup',
                            style='success',
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=texts.t('SUPPORT_BUTTON', '🆘 Поддержка'), callback_data='menu_support'
                        )
                    ],
                ]
            )

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'напоминание об истекшей подписке'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке напоминания об истекшей подписке пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
            return False
        except TelegramNetworkError as e:
            logger.warning(
                'Таймаут отправки напоминания об истекшей подписке пользователю', telegram_id=user.telegram_id, e=e
            )
            return False
        except Exception as e:
            logger.error(
                'Ошибка отправки напоминания об истекшей подписке пользователю', telegram_id=user.telegram_id, e=e
            )
            return False

    async def _send_expired_discount_notification(
        self,
        user: User,
        subscription: Subscription,
        percent: int,
        expires_at: datetime,
        offer_id: int,
        wave: str,
        trigger_days: int = None,
    ) -> bool:
        try:
            if not user.telegram_id:
                return await notification_delivery_service.send_notification(
                    user=user,
                    notification_type=NotificationType.WINBACK_DISCOUNT,
                    context={
                        'percent': percent,
                        'expires_at': format_local_datetime(expires_at, '%d.%m.%Y %H:%M'),
                        'trigger_days': trigger_days or '',
                    },
                )
            texts = get_texts(user.language)

            tariff_label = ''

            if wave == 'second':
                template = texts.get(
                    'SUBSCRIPTION_EXPIRED_SECOND_WAVE',
                    (
                        '🔥 <b>Скидка {percent}% на продление{tariff_label}</b>\n\n'
                        'Активируйте предложение, чтобы получить дополнительную скидку. '
                        'Она суммируется с вашей промогруппой и действует до {expires_at}.'
                    ),
                )
            else:
                template = texts.get(
                    'SUBSCRIPTION_EXPIRED_THIRD_WAVE',
                    (
                        '🎁 <b>Индивидуальная скидка {percent}%{tariff_label}</b>\n\n'
                        'Прошло {trigger_days} дней без подписки — возвращайтесь и активируйте дополнительную скидку. '
                        'Она суммируется с промогруппой и действует до {expires_at}.'
                    ),
                )

            message = template.format(
                percent=percent,
                expires_at=format_local_datetime(expires_at, '%d.%m.%Y %H:%M'),
                trigger_days=trigger_days or '',
                tariff_label=tariff_label,
            )

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    # Одна кнопка: она и закрепляет скидку, и ведёт к оплате.
                    [
                        build_miniapp_or_callback_button(
                            text=texts.t('DISCOUNT_RETURN_BUTTON', '🎁 Продлить со скидкой {percent}%').format(
                                percent=percent
                            ),
                            callback_data=f'claim_discount_{offer_id}',
                            style='success',
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=texts.t('SUPPORT_BUTTON', '🆘 Поддержка'), callback_data='menu_support'
                        )
                    ],
                ]
            )

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'скидочное уведомление'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке скидочного уведомления пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
            return False
        except TelegramNetworkError as e:
            logger.warning('Таймаут отправки скидочного уведомления пользователю', telegram_id=user.telegram_id, e=e)
            return False
        except Exception as e:
            logger.error('Ошибка отправки скидочного уведомления пользователю', telegram_id=user.telegram_id, e=e)
            return False

    async def _send_autopay_success_notification(self, user: User, amount: int, days: int):
        try:
            texts = get_texts(user.language)
            message = texts.AUTOPAY_SUCCESS.format(days=days, amount=settings.format_price(amount))
            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
            )
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if not await self._handle_unreachable_user(user, exc, 'уведомление об успешном автоплатеже'):
                logger.error(
                    'Ошибка Telegram API при отправке уведомления об автоплатеже пользователю',
                    telegram_id=user.telegram_id,
                    exc=exc,
                )
        except TelegramNetworkError as e:
            logger.warning(
                'Таймаут отправки уведомления об автоплатеже пользователю', telegram_id=user.telegram_id, e=e
            )
        except Exception as e:
            logger.error('Ошибка отправки уведомления об автоплатеже пользователю', telegram_id=user.telegram_id, e=e)

    async def _notify_autopay_cannot_renew(self, user, subscription, *, cause: str) -> None:
        """Разово сказать, что автопродление этой подписки не сработает само.

        Поводы — тариф отключён, цена не считается, у периода нет цены: деньги на
        балансе есть, но списания не будет, а напоминание за дни до конца обещало
        «ничего делать не нужно». Дедуп — одно сообщение на подписку за период
        (end_date): in-memory + Redis с TTL до конца срока + 3 дня. Сам метод в БД
        не ходит и исключений наружу не бросает.
        """
        try:
            if user is None or subscription is None or subscription.end_date is None:
                return
            if not NotificationSettingsService.are_notifications_globally_enabled():
                return
            cycle_token = int(subscription.end_date.timestamp())
            key = f'autopay_cannot_renew:{subscription.id}:{cycle_token}'
            sent = self.__dict__.setdefault('_autopay_cannot_renew_sent', set())
            if key in sent:
                return
            try:
                if await cache.exists(key):
                    sent.add(key)
                    return
            except Exception as redis_err:
                logger.debug('Redis недоступен для дедупа autopay_cannot_renew', error=redis_err)

            if user.telegram_id and not self.bot:
                return  # бота нет — не помечаем, попробуем в следующем цикле

            # Помечаем ДО отправки: «не больше одного раза» важнее доставки —
            # заблокировавший бота не должен получать попытку каждый цикл.
            sent.add(key)
            hours_left = max(0.0, (subscription.end_date - datetime.now(UTC)).total_seconds() / 3600.0)
            await cache.set(key, 1, expire=int(hours_left * 3600) + 72 * 3600)

            texts = get_texts(user.language)
            tariff_label = ''
            end_date = format_local_datetime(subscription.end_date, '%d.%m.%Y %H:%M')
            if user.telegram_id:
                from aiogram.types import InlineKeyboardMarkup

                message = texts.t(
                    'AUTOPAY_CANNOT_RENEW',
                    '⚠️ <b>Не получилось продлить подписку{tariff_label} автоматически</b>\n\n'
                    'Подписка действует до {end_date}. Чтобы VPN не отключился, '
                    'выберите тариф и продлите подписку по кнопке ниже.',
                ).format(tariff_label=tariff_label, end_date=end_date)
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            build_subscription_extend_button(
                                texts.t('BTN_RENEW_SUBSCRIPTION', '⏰ Продлить подписку'),
                                style='success',
                            )
                        ]
                    ]
                )
                await self._send_message_with_logo(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode='HTML',
                    reply_markup=keyboard,
                    user=user,
                )
            else:
                await notification_delivery_service.notify_autopay_failed(
                    user=user,
                    reason=texts.t(
                        'AUTOPAY_CANNOT_RENEW_REASON',
                        'Не получилось продлить подписку автоматически — выберите тариф и продлите её вручную',
                    ),
                )
            logger.info(
                '📨 Уведомление «автопродление не сработает» отправлено',
                subscription_id=subscription.id,
                user_id=user.id,
                cause=cause,
            )
        except Exception as error:
            logger.warning(
                'Не удалось отправить уведомление «автопродление не сработает»',
                subscription_id=getattr(subscription, 'id', None),
                cause=cause,
                error=error,
            )

    async def _send_autopay_failed_notification(
        self,
        user: User,
        balance: int,
        required: int,
        *,
        subscription: Subscription | None = None,
        is_final: bool = False,
    ) -> bool:
        """True — сообщение ушло (или человек недоступен и писать ему некуда)."""
        try:
            texts = get_texts(user.language)
            if is_final:
                template = texts.t(
                    'AUTOPAY_FAILED_FINAL',
                    '\n⏰ <b>Последнее напоминание</b>\n\n'
                    'Подписка скоро отключится — автоплатёж не прошёл из-за нехватки средств.\n'
                    'Баланс: {balance}\nТребуется: {required}\n\n'
                    'Пополните баланс сейчас, чтобы не потерять доступ.\n',
                )
            else:
                template = texts.AUTOPAY_FAILED
            message = template.format(balance=settings.format_price(balance), required=settings.format_price(required))

            from aiogram.types import InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [build_miniapp_or_callback_button(text='💳 Пополнить баланс', callback_data='balance_topup')],
                    [build_miniapp_or_callback_button(text='📱 Моя подписка', callback_data='menu_subscription')],
                ]
            )

            await self._send_message_with_logo(
                chat_id=user.telegram_id,
                text=message,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            if await self._handle_unreachable_user(user, exc, 'уведомление о неудачном автоплатеже'):
                return True
            logger.error(
                'Ошибка Telegram API при отправке уведомления о неудачном автоплатеже пользователю',
                telegram_id=user.telegram_id,
                exc=exc,
            )
        except TelegramNetworkError as e:
            logger.warning(
                'Таймаут отправки уведомления о неудачном автоплатеже пользователю', telegram_id=user.telegram_id, e=e
            )
        except Exception as e:
            logger.error(
                'Ошибка отправки уведомления о неудачном автоплатеже пользователю', telegram_id=user.telegram_id, e=e
            )
        return False

    async def _retry_stuck_guest_purchases(self, db: AsyncSession):
        from app.services.guest_purchase_service import (
            recover_stuck_pending_purchases,
            retry_stuck_paid_purchases,
            retry_stuck_pending_activation,
        )

        # Phase 1: Recover PENDING purchases where provider payment already succeeded
        try:
            recovered = await recover_stuck_pending_purchases(db, stale_minutes=10, limit=10)
            if recovered:
                logger.info('Recovered stuck PENDING purchases', recovered=recovered)
        except Exception:
            logger.error('Error recovering stuck PENDING guest purchases', exc_info=True)
            await _rollback_quietly(db, step='guest_purchases')

        # Phase 2: Retry fulfillment for purchases in PAID status
        try:
            retried = await retry_stuck_paid_purchases(db, stale_minutes=5, limit=10)
            if retried:
                logger.info('Retried stuck guest purchases', retried=retried)
        except Exception:
            logger.error('Error retrying stuck PAID guest purchases', exc_info=True)
            await _rollback_quietly(db, step='guest_purchases')

        # Phase 3: Retry activation for purchases in PENDING_ACTIVATION status
        try:
            retried_pa = await retry_stuck_pending_activation(db, stale_minutes=10, limit=10)
            if retried_pa:
                logger.info('Retried stuck pending_activation purchases', retried=retried_pa)
        except Exception:
            logger.error('Error retrying stuck PENDING_ACTIVATION guest purchases', exc_info=True)
            await _rollback_quietly(db, step='guest_purchases')

    async def _check_traffic_warnings(self, db: AsyncSession):
        """Check subscriptions approaching traffic limit and notify users."""
        if not self.bot or not NotificationSettingsService.are_notifications_globally_enabled():
            return

        # Не срочно: ночью не будим, письмо уйдёт утром (ключ «уже отправлено» ещё не стоит).
        from app.utils.quiet_hours import is_quiet_time
        from app.utils.timezone import get_local_timezone

        if is_quiet_time(
            datetime.now(UTC),
            start_hour=settings.USER_REMINDERS_QUIET_HOURS_START,
            end_hour=settings.USER_REMINDERS_QUIET_HOURS_END,
            tz=get_local_timezone(),
        ):
            return

        try:
            from aiogram.types import InlineKeyboardMarkup
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            from app.database.models import Subscription
            from app.services.bypass_downgrade import has_bypass_quota
            from app.utils.notification_prefs import get_traffic_warning_percent, is_traffic_warning_enabled

            # Get active subscriptions with traffic limits (not unlimited)
            result = await db.execute(
                select(Subscription)
                .options(selectinload(Subscription.user))
                .where(
                    Subscription.status.in_(['active', 'trial']),
                    Subscription.traffic_limit_gb > 0,
                )
            )
            subscriptions = result.scalars().all()

            sent_count = 0
            for subscription in subscriptions:
                user = subscription.user
                if not user or not user.telegram_id:
                    continue
                if user.status in (UserStatus.BLOCKED.value, UserStatus.DELETED.value):
                    continue

                if not is_traffic_warning_enabled(user):
                    continue

                traffic_limit = subscription.traffic_limit_gb or 0
                traffic_used = subscription.traffic_used_gb or 0.0

                if traffic_limit <= 0:
                    continue

                current_percent = (traffic_used / traffic_limit) * 100
                user_threshold = get_traffic_warning_percent(user)

                # На нуле приходит своё сообщение («Обходы отключены» / «трафик закончился»):
                # «почти исчерпан» после него только путает.
                if current_percent < user_threshold or current_percent >= 100:
                    continue

                # Один раз на порог (до смены лимита — докупки или нового периода), а не каждые
                # сутки, пока трафик выше порога. Ключ общий с вебхуком панели о пороге: если
                # панель уже написала, второе письмо не уходит.
                cache_key_str = traffic_warning_cache_key(subscription.id, traffic_limit)
                if await self._is_marked(cache_key_str):
                    continue
                if await self._is_marked(telegram_blocked_cache_key(user.telegram_id)):
                    continue

                try:
                    language = getattr(user, 'language', 'ru') or 'ru'
                    texts = get_texts(language)
                    left_gb = f'{max(0.0, traffic_limit - traffic_used):.1f}'.rstrip('0').rstrip('.')
                    # Тот же текст, что у порога из панели: остаток в ГБ и что будет на нуле —
                    # на тарифе с обходами отключатся только обходы, обычные серверы работают.
                    note = texts.t(
                        'WEBHOOK_BANDWIDTH_NOTE_BYPASS'
                        if has_bypass_quota(subscription)
                        else 'WEBHOOK_BANDWIDTH_NOTE_REGULAR',
                        '',
                    )
                    message = texts.t(
                        'WEBHOOK_SUB_BANDWIDTH_THRESHOLD',
                        '📊 <b>Израсходовано {percent}% трафика</b>\n\nОсталось около <b>{left} ГБ</b>.{note}',
                    ).format(percent=f'{current_percent:.0f}', left=left_gb, note=note)
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                build_miniapp_or_callback_button(
                                    text=texts.t('BUY_TRAFFIC_BUTTON', '📈 Докупить трафик'),
                                    callback_data='buy_traffic',
                                    style='success',
                                )
                            ],
                        ]
                    )
                    await self.bot.send_message(
                        user.telegram_id,
                        message,
                        parse_mode='HTML',
                        reply_markup=keyboard,
                    )
                    await self._set_mark(cache_key_str, TRAFFIC_WARNING_TTL_SECONDS)
                    sent_count += 1
                except Exception as send_error:
                    await self._remember_if_unreachable(user, send_error)
                    logger.debug(
                        'Failed to send traffic warning',
                        user_id=user.id,
                        subscription_id=subscription.id,
                        error=send_error,
                    )

            if sent_count > 0:
                logger.info('Traffic warnings sent', sent_count=sent_count)

        except Exception as error:
            logger.error('Error checking traffic warnings', error=error)
            await _rollback_quietly(db, step='traffic_warnings')

    async def _check_low_balance_alerts(self, db: AsyncSession):
        """Check users with autopay enabled who have low balance and notify them.

        Guards:
        - Disabled by default; users opt-in via cabinet notification settings
        - Only alerts when subscription expires within LOW_BALANCE_ALERT_EXPIRY_DAYS (default 3)
        - Quiet hours: skips sending between 22:00 and 09:00 server time
        - Rate-limited: max 1 alert per 24 hours per user
        """
        if not self.bot or not NotificationSettingsService.are_notifications_globally_enabled():
            return

        try:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
            from sqlalchemy import select

            from app.database.models import Subscription, User
            from app.utils.notification_prefs import get_balance_low_threshold, is_balance_low_enabled

            # Quiet hours: don't disturb users at night (22:00-09:00 UTC)
            current_hour = datetime.now(UTC).hour
            if current_hour >= 22 or current_hour < 9:
                return

            # Only alert for subscriptions expiring soon (default 3 days)
            expiry_days = settings.LOW_BALANCE_ALERT_EXPIRY_DAYS
            expiry_threshold = datetime.now(UTC) + timedelta(days=expiry_days)

            result = await db.execute(
                select(User)
                .join(Subscription, Subscription.user_id == User.id)
                .where(
                    Subscription.status.in_(['active', 'trial']),
                    Subscription.autopay_enabled.is_(True),
                    Subscription.end_date.isnot(None),
                    Subscription.end_date <= expiry_threshold,
                    User.telegram_id.isnot(None),
                )
                .distinct()
            )
            users = result.scalars().all()

            sent_count = 0
            for user in users:
                if user.status in (UserStatus.BLOCKED.value, UserStatus.DELETED.value):
                    continue
                if not is_balance_low_enabled(user):
                    continue

                threshold = get_balance_low_threshold(user)
                balance = int(getattr(user, 'balance_kopeks', 0) or 0)

                if balance >= threshold:
                    continue

                # Rate-limit via Redis: max 1 notification per 24 hours per user
                cache_key_str = f'low_balance_alert:{user.id}'
                if await self._is_marked(cache_key_str):
                    continue
                if await self._is_marked(telegram_blocked_cache_key(user.telegram_id)):
                    continue

                try:
                    language = getattr(user, 'language', 'ru') or 'ru'
                    texts = get_texts(language)
                    threshold_rub = threshold / 100
                    balance_rub = balance / 100
                    message = texts.get(
                        'LOW_BALANCE_ALERT',
                        '⚠️ <b>Низкий баланс</b>\n\n'
                        'Ваш баланс: {balance} ₽\n'
                        'Порог уведомления: {threshold} ₽\n\n'
                        'Пополните баланс, чтобы автопродление подписки прошло успешно.',
                    )
                    message = message.format(
                        balance=f'{balance_rub:.0f}',
                        threshold=f'{threshold_rub:.0f}',
                    )

                    # Build inline keyboard with cabinet top-up button
                    keyboard = None
                    miniapp_url = settings.get_main_menu_miniapp_url()
                    if miniapp_url:
                        topup_label = texts.get('LOW_BALANCE_TOPUP_BUTTON', '💳 Пополнить баланс')
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text=topup_label,
                                        web_app=WebAppInfo(url=miniapp_url),
                                    )
                                ]
                            ]
                        )

                    await self.bot.send_message(
                        user.telegram_id,
                        message,
                        parse_mode='HTML',
                        reply_markup=keyboard,
                    )
                    # Mark as sent for 24 hours
                    await self._set_mark(cache_key_str, LOW_BALANCE_ALERT_TTL_SECONDS)
                    sent_count += 1
                except Exception as send_error:
                    await self._remember_if_unreachable(user, send_error)
                    logger.debug('Failed to send low balance alert', user_id=user.id, error=send_error)

            if sent_count > 0:
                logger.info('Low balance alerts sent', sent_count=sent_count)

        except Exception as error:
            logger.error('Error checking low balance alerts', error=error)
            await _rollback_quietly(db, step='low_balance_alerts')

    async def _cleanup_expired_refresh_tokens(self, db: AsyncSession):
        """Delete expired and revoked refresh tokens to prevent table bloat."""
        try:
            from sqlalchemy import delete

            from app.database.models import CabinetRefreshToken

            now = datetime.now(UTC)
            # Delete tokens that are either expired or revoked more than 24h ago
            stmt = delete(CabinetRefreshToken).where(
                (CabinetRefreshToken.expires_at < now) | (CabinetRefreshToken.revoked_at < now - timedelta(hours=24))
            )
            result = await db.execute(stmt)
            deleted = result.rowcount
            if deleted > 0:
                await db.commit()
                logger.info('Cleaned up expired/revoked refresh tokens', deleted_count=deleted)
        except Exception as error:
            logger.error('Error cleaning up refresh tokens', error=error)
            try:
                await db.rollback()
            except Exception:
                logger.debug('Ignored error in _cleanup_expired_refresh_tokens', exc_info=True)

    async def _cleanup_button_click_logs(self, db: AsyncSession):
        """Чистит старые записи лога действий юзеров (USER_ACTION_LOG_RETENTION_DAYS)."""
        try:
            retention_days = settings.USER_ACTION_LOG_RETENTION_DAYS
            if retention_days <= 0:
                return

            now = datetime.now(UTC)
            if now.hour != 4:
                return

            from sqlalchemy import delete

            from app.database.models import ButtonClickLog

            stmt = delete(ButtonClickLog).where(ButtonClickLog.clicked_at < now - timedelta(days=retention_days))
            result = await db.execute(stmt)
            deleted = result.rowcount
            if deleted > 0:
                await db.commit()
                logger.info('Очищены старые записи лога действий', deleted_count=deleted)
        except Exception as error:
            logger.error('Ошибка очистки лога действий', error=error)
            try:
                await db.rollback()
            except Exception:
                logger.debug('Ignored error in _cleanup_button_click_logs', exc_info=True)

    async def _sync_with_remnawave(self, db: AsyncSession):
        try:
            now = datetime.now(UTC)
            if now.minute != 0:
                return

            if not self.subscription_service.is_configured:
                logger.warning('RemnaWave API не настроен. Пропускаем синхронизацию')
                return

            async with self.subscription_service.get_api_client() as api:
                system_stats = await api.get_system_stats()

                await self._log_monitoring_event(
                    db, 'remnawave_sync', 'Синхронизация с RemnaWave завершена', {'stats': system_stats}
                )

        except Exception as e:
            logger.error('Ошибка синхронизации с RemnaWave', error=e)
            await _rollback_quietly(db, step='remnawave_sync')
            await self._log_monitoring_event(
                db,
                'remnawave_sync_error',
                f'Ошибка синхронизации с RemnaWave: {e!s}',
                {'error': str(e)},
                is_success=False,
            )

    async def _check_ticket_sla(self, db: AsyncSession):
        try:
            # Quick guards
            # Allow runtime toggle from SupportSettingsService
            try:
                from app.services.support_settings_service import SupportSettingsService

                sla_enabled_runtime = SupportSettingsService.get_sla_enabled()
            except Exception:
                sla_enabled_runtime = settings.SUPPORT_TICKET_SLA_ENABLED
            if not sla_enabled_runtime:
                return
            if not self.bot:
                return
            if not settings.is_admin_notifications_enabled():
                return

            try:
                from app.services.support_settings_service import SupportSettingsService

                sla_minutes = max(1, int(SupportSettingsService.get_sla_minutes()))
            except Exception:
                sla_minutes = max(1, int(settings.SUPPORT_TICKET_SLA_MINUTES))
            cooldown_minutes = max(1, int(settings.SUPPORT_TICKET_SLA_REMINDER_COOLDOWN_MINUTES))
            now = datetime.now(UTC)
            stale_before = now - timedelta(minutes=sla_minutes)
            cooldown_before = now - timedelta(minutes=cooldown_minutes)

            # Tickets to remind: open, no admin reply yet after user's last message (status OPEN), stale by SLA,
            # and either never reminded or cooldown passed
            result = await db.execute(
                select(Ticket)
                .options(selectinload(Ticket.user))
                .where(
                    and_(
                        Ticket.status == TicketStatus.OPEN.value,
                        Ticket.updated_at <= stale_before,
                        or_(Ticket.last_sla_reminder_at.is_(None), Ticket.last_sla_reminder_at <= cooldown_before),
                    )
                )
            )
            tickets = result.scalars().all()
            if not tickets:
                return

            from app.services.admin_notification_service import AdminNotificationService

            reminders_sent = 0
            service = AdminNotificationService(self.bot)

            for ticket in tickets:
                try:
                    waited_minutes = max(0, int((now - ticket.updated_at).total_seconds() // 60))
                    title = (ticket.title or '').strip()
                    if len(title) > 60:
                        title = title[:57] + '...'

                    # Детали пользователя: имя, Telegram ID и username
                    full_name = html.escape(ticket.user.full_name or '') if ticket.user else 'Unknown'
                    telegram_id_display = ticket.user.telegram_id if ticket.user else '—'
                    username_display = format_username_link(
                        ticket.user.username if ticket.user else None, 'отсутствует'
                    )
                    safe_title = html.escape(title) if title else '—'

                    text = (
                        f'⏰ <b>Ожидание ответа на тикет превышено</b>\n\n'
                        f'🆔 <b>ID:</b> <code>{ticket.id}</code>\n'
                        f'👤 <b>Пользователь:</b> {full_name}\n'
                        f'🆔 <b>Telegram ID:</b> <code>{telegram_id_display}</code>\n'
                        f'📱 <b>Username:</b> {username_display}\n'
                        f'📝 <b>Заголовок:</b> {safe_title}\n'
                        f'⏱️ <b>Ожидает ответа:</b> {waited_minutes} мин\n'
                    )

                    sent = await service.send_ticket_event_notification(text)
                    if sent:
                        ticket.last_sla_reminder_at = now
                        reminders_sent += 1
                        # commit after each to persist timestamp and avoid duplicate reminders on crash
                        await db.commit()
                except Exception as notify_error:
                    logger.error(
                        'Ошибка отправки SLA-уведомления по тикету', ticket_id=ticket.id, notify_error=notify_error
                    )

            if reminders_sent > 0:
                await self._log_monitoring_event(
                    db,
                    'ticket_sla_reminders_sent',
                    f'Отправлено {reminders_sent} SLA-напоминаний по тикетам',
                    {'count': reminders_sent},
                )
        except Exception as e:
            logger.error('Ошибка проверки SLA тикетов', error=e)

    async def _sla_loop(self):
        try:
            interval_seconds = max(10, int(settings.SUPPORT_TICKET_SLA_CHECK_INTERVAL_SECONDS))
        except Exception:
            interval_seconds = 60
        while self.is_running:
            try:
                async with AsyncSessionLocal() as db:
                    try:
                        await self._check_ticket_sla(db)
                        await db.commit()
                    except Exception as e:
                        logger.error('Ошибка в SLA-проверке', error=e)
                        await db.rollback()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Ошибка в SLA-цикле', error=e)
            await asyncio.sleep(interval_seconds)

    async def _check_withdrawal_reminders(self, db: AsyncSession) -> int:
        """Напоминает админам о заявках на вывод, которые ждут решения дольше лимита.

        Механика повторяет SLA тикетов (_check_ticket_sla): заявка в статусе pending
        старше REFERRAL_WITHDRAWAL_REMINDER_MINUTES получает напоминание, следующее —
        не раньше чем через REFERRAL_WITHDRAWAL_REMINDER_COOLDOWN_MINUTES. Решение по
        заявке меняет статус, и напоминания прекращаются сами. Возвращает число
        отправленных напоминаний.
        """
        try:
            if not settings.REFERRAL_WITHDRAWAL_REMINDER_ENABLED:
                return 0
            if not self.bot:
                return 0
            if not settings.is_admin_notifications_enabled():
                return 0

            wait_minutes = max(1, int(settings.REFERRAL_WITHDRAWAL_REMINDER_MINUTES))
            cooldown_minutes = max(1, int(settings.REFERRAL_WITHDRAWAL_REMINDER_COOLDOWN_MINUTES))
            now = datetime.now(UTC)
            stale_before = now - timedelta(minutes=wait_minutes)
            cooldown_before = now - timedelta(minutes=cooldown_minutes)

            result = await db.execute(
                select(WithdrawalRequest)
                .options(selectinload(WithdrawalRequest.user))
                .where(
                    and_(
                        WithdrawalRequest.status == WithdrawalRequestStatus.PENDING.value,
                        WithdrawalRequest.created_at <= stale_before,
                        or_(
                            WithdrawalRequest.last_reminder_at.is_(None),
                            WithdrawalRequest.last_reminder_at <= cooldown_before,
                        ),
                    )
                )
                .order_by(WithdrawalRequest.created_at.asc())
            )
            requests = result.scalars().all()
            if not requests:
                return 0

            from app.services.admin_notification_service import AdminNotificationService

            service = AdminNotificationService(self.bot)
            reminders_sent = 0
            for request in requests:
                try:
                    waited_minutes = max(0, int((now - request.created_at).total_seconds() // 60))
                    sent = await service.send_withdrawal_pending_reminder(request, waited_minutes)
                    if sent:
                        request.last_reminder_at = now
                        reminders_sent += 1
                        # commit после каждой, чтобы при падении не задвоить напоминание
                        await db.commit()
                except Exception as notify_error:
                    logger.error(
                        'Ошибка отправки напоминания о заявке на вывод',
                        request_id=request.id,
                        notify_error=notify_error,
                    )

            if reminders_sent > 0:
                await self._log_monitoring_event(
                    db,
                    'withdrawal_reminders_sent',
                    f'Отправлено {reminders_sent} напоминаний о заявках на вывод',
                    {'count': reminders_sent},
                )
            return reminders_sent
        except Exception as e:
            logger.error('Ошибка проверки заявок на вывод без решения', error=e)
            return 0

    async def _withdrawal_reminder_loop(self):
        while self.is_running:
            try:
                async with AsyncSessionLocal() as db:
                    try:
                        await self._check_withdrawal_reminders(db)
                        await db.commit()
                    except Exception as e:
                        logger.error('Ошибка в проверке заявок на вывод', error=e)
                        await db.rollback()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Ошибка в цикле напоминаний о заявках на вывод', error=e)
            # Интервал читается на каждом круге: правка из кабинета применяется без перезапуска
            try:
                interval_seconds = max(10, int(settings.REFERRAL_WITHDRAWAL_REMINDER_CHECK_INTERVAL_SECONDS))
            except Exception:
                interval_seconds = 60
            await asyncio.sleep(interval_seconds)

    async def _abandoned_payment_loop(self):
        """Напоминание о брошенной оплате: каждые 2 минуты, чтобы поймать 10-ю минуту после платежа."""
        from app.services.activation_funnel_service import ActivationFunnelService

        while self.is_running:
            try:
                if self.bot:
                    funnel = ActivationFunnelService(bot=self.bot, send_func=self._send_message_with_logo)
                    async with AsyncSessionLocal() as db:
                        for step in (
                            funnel.process_abandoned_payments,
                            funnel.process_abandoned_carts,
                            funnel.process_referral_prompt,
                        ):
                            try:
                                await step(db)
                            except Exception as e:
                                logger.warning(
                                    'Сбой напоминания (брошенная оплата, корзина, приглашение)', error=str(e)
                                )
                                await db.rollback()
                        # Вторые волны — реже: раз в 30 минут достаточно (задержка у них ~сутки).
                        if datetime.now(UTC) >= self._last_abandoned_wave2 + timedelta(minutes=30):
                            self._last_abandoned_wave2 = datetime.now(UTC)
                            for step in (
                                funnel.process_abandoned_payments_wave2,
                                funnel.process_abandoned_carts_wave2,
                            ):
                                try:
                                    await step(db)
                                except Exception as e:
                                    logger.warning('Сбой напоминания (вторая волна)', error=str(e))
                                    await db.rollback()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning('Ошибка в цикле напоминаний о брошенной оплате', error=str(e))
            await asyncio.sleep(120)

    async def _log_monitoring_event(
        self, db: AsyncSession, event_type: str, message: str, data: dict[str, Any] = None, is_success: bool = True
    ):
        try:
            log_entry = MonitoringLog(event_type=event_type, message=message, data=data or {}, is_success=is_success)

            db.add(log_entry)
            await db.commit()

        except Exception as e:
            logger.error('Ошибка логирования события мониторинга', error=e)
            await _rollback_quietly(db, step='monitoring_log')


monitoring_service = MonitoringService()
