"""Spofy: перевод в Bypass-Off и обратно — с базой, панелью и уведомлениями.

Правила — в ``app/services/bypass_downgrade.py``. Здесь:

- ``suspend`` — вебхук ``user.limited`` (или сверка) на подписке с обходами:
  пометка ``bypass_suspended_at``, статус остаётся ACTIVE, пуш в панель (уходит
  Bypass-Off и безлимит), сообщение человеку;
- ``restore`` — снять пометку и запушить сквады тарифа; сообщение «обходы снова
  работают», если подписка жива;
- ``reconcile`` — фоновая сверка раз в ``BYPASS_RECONCILE_INTERVAL_MINUTES``:
  чинит пропущенные вебхуки и расхождения в обе стороны, идемпотентна.

Панель пишет только ``SubscriptionService.update_remnawave_user`` — общий
писатель, через который идут все пуши (см. tests/services/panel_sync/test_no_bypass.py).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database.models import Subscription, SubscriptionStatus
from app.localization.texts import get_texts
from app.services import bypass_downgrade as rules
from app.services.notification_delivery_service import notification_delivery_service
from app.services.notification_types import NotificationType
from app.utils.miniapp_buttons import build_miniapp_or_callback_button, build_subscription_extend_button


logger = structlog.get_logger(__name__)

_BATCH = 200
#: Предупреждение о расхождении инбаундов Bypass-Off и обычного сквада — не чаще раза в час.
_SQUAD_DRIFT_WARN_EVERY_SECONDS = 3600


class BypassDowngradeService:
    def __init__(self) -> None:
        self.bot: Bot | None = None
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._last_drift_warning = 0.0

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    # Переходы
    # ------------------------------------------------------------------ #
    async def suspend(
        self,
        db: AsyncSession,
        user,
        subscription: Subscription,
        *,
        source: str,
        panel_used_gb: float | None = None,
        notify: bool = True,
    ) -> bool:
        """Перевести подписку в Bypass-Off. Вызывающий проверил ``is_enforcing``
        и ``ineligibility_reason``. Возвращает True, если панель приняла пуш."""
        now = datetime.now(UTC)
        if panel_used_gb is not None and panel_used_gb > (subscription.traffic_used_gb or 0.0):
            subscription.traffic_used_gb = panel_used_gb
        if not rules.quota_exhausted(subscription):
            # Панель уже сказала «лимит» (LIMITED / вебхук), а расход в боте отстал:
            # верим панели, иначе пометка не подействует и панель выключит всё.
            subscription.traffic_used_gb = float(subscription.traffic_limit_gb or 0)
        already = subscription.bypass_suspended_at is not None
        if not already:
            subscription.bypass_suspended_at = now
        if subscription.status == SubscriptionStatus.LIMITED.value:
            subscription.status = SubscriptionStatus.ACTIVE.value
        # Не грейс: человек не потерял доступ, обычные серверы работают.
        subscription.grace_candidate_reason = None
        subscription.grace_candidate_at = None
        subscription.updated_at = now
        await db.commit()

        pushed = await self._push(db, subscription)
        logger.info(
            'Обходы отключены: исчерпан трафик',
            subscription_id=subscription.id,
            user_id=subscription.user_id,
            source=source,
            pushed=pushed,
            repeat=already,
        )
        if notify and not already:
            key = 'BYPASS_SUSPENDED_TRIAL' if getattr(subscription, 'is_trial', False) else 'BYPASS_SUSPENDED'
            await self.notify(user, key, subscription)
        return pushed

    async def restore(
        self,
        db: AsyncSession,
        user,
        subscription: Subscription,
        *,
        source: str,
        notify: bool = True,
    ) -> bool:
        """Снять пометку и вернуть сквады тарифа в панель."""
        if subscription.bypass_suspended_at is None:
            return True
        subscription.bypass_suspended_at = None
        subscription.updated_at = datetime.now(UTC)
        await db.commit()

        pushed = await self._push(db, subscription)
        logger.info(
            'Обходы возвращены',
            subscription_id=subscription.id,
            user_id=subscription.user_id,
            source=source,
            pushed=pushed,
        )
        if notify and subscription.actual_status == 'active':
            await self.notify(user, 'BYPASS_RESTORED', subscription)
        return pushed

    async def _push(self, db: AsyncSession, subscription: Subscription) -> bool:
        from app.services.subscription_service import SubscriptionService

        try:
            return await SubscriptionService().update_remnawave_user(db, subscription) is not None
        except Exception as error:
            logger.warning('Bypass-Off: пуш в панель не прошёл', subscription_id=subscription.id, error=str(error))
            return False

    # ------------------------------------------------------------------ #
    # Вебхуки
    # ------------------------------------------------------------------ #
    async def handle_limited_webhook(self, db: AsyncSession, user, subscription: Subscription, data: dict) -> bool:
        """``user.limited``: True — обработано здесь, прежний путь (LIMITED, грейс,
        WEBHOOK_SUB_LIMITED) пропустить."""
        if not (rules.is_enforcing() or rules.is_observing()):
            return False
        tariff = await self._load_tariff(db, subscription)
        reason = rules.ineligibility_reason(user, subscription, tariff=tariff)
        if reason is not None:
            logger.info('Bypass-Off: подписка не подходит', subscription_id=subscription.id, reason=reason)
            return False
        if rules.is_observing():
            logger.info('Bypass-Off (observe): отключили бы обходы', subscription_id=subscription.id, source='webhook')
            return False
        await self.suspend(db, user, subscription, source='webhook', panel_used_gb=_panel_used_gb(data))
        return True

    async def handle_traffic_reset_webhook(self, db: AsyncSession, user, subscription: Subscription) -> bool:
        """``user.traffic_reset`` (расход уже обнулён): True — человеку ушло
        «обходы снова работают», обычное «трафик сброшен» не нужно."""
        if getattr(subscription, 'bypass_suspended_at', None) is None:
            return False
        await self.restore(db, user, subscription, source='webhook_traffic_reset')
        return subscription.actual_status == 'active'

    # ------------------------------------------------------------------ #
    # Сверка
    # ------------------------------------------------------------------ #
    async def reconcile(self, db: AsyncSession) -> dict[str, int]:
        stats = {'restored': 0, 'cleared': 0, 'resuspended': 0, 'suspended': 0, 'would_suspend': 0}
        now = datetime.now(UTC)

        flagged = await self._load(db, Subscription.bypass_suspended_at.isnot(None))
        for subscription in flagged:
            user = subscription.user
            if not rules.is_enforcing():
                # Откат (режим false): снимаем пометки молча — дальше прежнее поведение.
                await self.restore(db, user, subscription, source='reconcile_disabled', notify=False)
                stats['cleared'] += 1
            elif subscription.actual_status not in ('active', 'limited'):
                # Истекла / отключена: обходы тут ни при чём, продление начнёт с чистого листа.
                await self.restore(db, user, subscription, source='reconcile_not_live', notify=False)
                stats['cleared'] += 1
            elif not rules.quota_exhausted(subscription):
                # Докупили трафик, продлили, сбросили расход — обходам можно вернуться.
                await self.restore(db, user, subscription, source='reconcile')
                stats['restored'] += 1
            elif subscription.status == SubscriptionStatus.LIMITED.value:
                # Импорт принёс LIMITED: прошлый пуш не дошёл, панель выключила всё.
                await self.suspend(db, user, subscription, source='reconcile_repush')
                stats['resuspended'] += 1

        if rules.is_enforcing() or rules.is_observing():
            candidates = await self._load(
                db,
                and_(
                    Subscription.bypass_suspended_at.is_(None),
                    Subscription.is_trial.is_(False),
                    Subscription.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.LIMITED.value]),
                    Subscription.traffic_limit_gb > 0,
                    Subscription.end_date > now,
                    or_(
                        Subscription.status == SubscriptionStatus.LIMITED.value,
                        Subscription.traffic_used_gb >= Subscription.traffic_limit_gb - 0.01,
                    ),
                ),
            )
            for subscription in candidates:
                user = subscription.user
                if rules.ineligibility_reason(user, subscription, tariff=subscription.tariff, now=now) is not None:
                    continue
                if rules.is_observing():
                    stats['would_suspend'] += 1
                    continue
                await self.suspend(db, user, subscription, source='reconcile')
                stats['suspended'] += 1

            await self._check_squad_drift()
        return stats

    async def _load(self, db: AsyncSession, condition) -> list[Subscription]:
        result = await db.execute(
            select(Subscription)
            .where(condition)
            .options(selectinload(Subscription.user), selectinload(Subscription.tariff))
            .order_by(Subscription.id)
            .limit(_BATCH)
        )
        return list(result.scalars().all())

    async def _load_tariff(self, db: AsyncSession, subscription: Subscription):
        if subscription.tariff_id is None:
            return None
        try:
            await db.refresh(subscription, ['tariff'])
        except Exception:
            return None
        return subscription.tariff

    async def _check_squad_drift(self) -> None:
        """Bypass-Off обязан держать те же инбаунды, что обычный сквад: иначе в
        Bypass-Off люди либо теряют обычный сервер, либо получают обход. Сверка
        ручная (панель не связывает сквады), поэтому только предупреждаем."""
        fallback = settings.BYPASS_FALLBACK_SQUAD_UUID
        if not fallback or time.monotonic() - self._last_drift_warning < _SQUAD_DRIFT_WARN_EVERY_SECONDS:
            return
        from app.services.remnawave_service import RemnaWaveService

        try:
            async with RemnaWaveService().get_api_client() as api:
                off = await api.get_internal_squad_by_uuid(settings.BYPASS_OFF_SQUAD_UUID)
                regular = await api.get_internal_squad_by_uuid(fallback)
        except Exception as error:
            logger.warning('Bypass-Off: не удалось сверить инбаунды сквадов', error=str(error))
            return
        if off is None or regular is None:
            logger.warning(
                'Bypass-Off: сквад не найден в панели', off_found=off is not None, fallback_found=regular is not None
            )
            self._last_drift_warning = time.monotonic()
            return
        off_inbounds = {inbound.uuid for inbound in off.inbounds}
        regular_inbounds = {inbound.uuid for inbound in regular.inbounds}
        if off_inbounds != regular_inbounds:
            logger.warning(
                'Bypass-Off: инбаунды не совпадают с обычным сквадом — синхронизируйте сквады в панели',
                only_in_bypass_off=sorted(off_inbounds - regular_inbounds),
                only_in_fallback=sorted(regular_inbounds - off_inbounds),
            )
            self._last_drift_warning = time.monotonic()

    # ------------------------------------------------------------------ #
    # Уведомления
    # ------------------------------------------------------------------ #
    async def notify(self, user, text_key: str, subscription: Subscription | None = None) -> None:
        if user is None:
            return
        texts = get_texts(getattr(user, 'language', None))
        message = texts.get(text_key)
        if not message:
            logger.warning('Bypass-Off: нет текста', text_key=text_key, language=getattr(user, 'language', None))
            return
        if text_key == 'BYPASS_SUSPENDED_TRIAL':
            # Пробному докупить трафик нельзя — путь назад к обходам один: тариф.
            rows = [
                [
                    build_miniapp_or_callback_button(
                        text=texts.get('BYPASS_TRIAL_BUY_BUTTON', '🏴‍☠️ Оформить «С Обходами»'),
                        callback_data='menu_buy',
                    )
                ]
            ]
            notification_type = NotificationType.WEBHOOK_SUB_LIMITED
        elif text_key == 'BYPASS_SUSPENDED':
            rows = [
                [
                    build_miniapp_or_callback_button(
                        text=texts.get('BYPASS_BUY_TRAFFIC_BUTTON', '📈 Докупить трафик'), callback_data='buy_traffic'
                    )
                ],
                [
                    build_subscription_extend_button(
                        texts.get('BYPASS_RENEW_BUTTON', '⏰ Продлить подписку'),
                        getattr(subscription, 'id', None),
                    )
                ],
            ]
            notification_type = NotificationType.WEBHOOK_SUB_LIMITED
        else:
            rows = [
                [
                    build_miniapp_or_callback_button(
                        text=texts.get('MY_SUBSCRIPTION_BUTTON', '📱 Моя подписка'), callback_data='menu_subscription'
                    )
                ]
            ]
            notification_type = NotificationType.WEBHOOK_SUB_TRAFFIC_RESET
        rows.append(
            [InlineKeyboardButton(text=texts.get('WEBHOOK_CLOSE_BUTTON', '✖️ Закрыть'), callback_data='webhook:close')]
        )
        try:
            await notification_delivery_service.send_notification(
                user=user,
                notification_type=notification_type,
                context={'text_key': text_key},
                bot=self.bot,
                telegram_message=message,
                telegram_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        except Exception:
            logger.exception('Bypass-Off: уведомление не доставлено', user_id=getattr(user, 'id', None))

    # ------------------------------------------------------------------ #
    # Жизненный цикл
    # ------------------------------------------------------------------ #
    def start_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        from app.database.database import AsyncSessionLocal

        self._stop_event = asyncio.Event()
        interval = max(1, settings.BYPASS_RECONCILE_INTERVAL_MINUTES) * 60
        logger.info(
            'Bypass-Off: сверка запущена',
            mode=rules.mode(),
            configured=rules.is_configured(),
            interval_min=interval // 60,
        )
        try:
            while not self._stop_event.is_set():
                # Режим читается на каждом проходе: его меняют из админки без рестарта,
                # а при false сверка должна снять оставшиеся пометки.
                if rules.is_configured() or rules.mode() == 'false':
                    try:
                        async with AsyncSessionLocal() as db:
                            stats = await self.reconcile(db)
                        if any(stats.values()):
                            logger.info('Bypass-Off: сверка', mode=rules.mode(), **stats)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        logger.error('Bypass-Off: ошибка сверки', error=str(error), exc_info=True)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.info('Bypass-Off: сверка остановлена')
            raise


def _panel_used_gb(data: dict) -> float | None:
    """Расход из тела вебхука (байты), если панель его прислала."""
    for key in ('usedTrafficBytes', 'used_traffic_bytes'):
        value = data.get(key)
        if value is None and isinstance(data.get('userTraffic'), dict):
            value = data['userTraffic'].get(key)
        if value is not None:
            try:
                return int(value) / 1024**3
            except (TypeError, ValueError):
                return None
    return None


bypass_downgrade_service = BypassDowngradeService()
