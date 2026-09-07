"""Сервис автоматической защиты от абуза триалов.

Каждые TRIAL_ABUSE_INTERVAL_HOURS часов (по умолчанию 4):
1. Забирает из панели RemnaWave все HWID-устройства и пользователей.
2. Ищет аккаунты-«близнецы» на одном устройстве (один HWID на 2+ аккаунта),
   а также пользователей бота с 2+ триальными подписками.
3. НИКОГДА не трогает платных пользователей и аккаунты, которых нет в БД бота.
4. Отправляет нарушителю предупреждение в Telegram и применяет действие:
   - expire  — «обнуление» подписки (доступ пропадает через ~30 секунд);
   - disable — полная блокировка аккаунта в панели.

Настройки (.env):
    TRIAL_ABUSE_ENABLED=true           # вкл/выкл сервис (по умолчанию выкл)
    TRIAL_ABUSE_INTERVAL_HOURS=4       # интервал проверки, часов
    TRIAL_ABUSE_ACTION=expire          # expire | disable
    TRIAL_ABUSE_NOTIFY=true            # слать предупреждение абузеру в Telegram
    TRIAL_ABUSE_MIN_ACCOUNTS=2         # минимум аккаунтов на HWID для реакции
    TRIAL_ABUSE_START_DELAY_MINUTES=5  # пауза после старта бота перед 1-й проверкой
    TRIAL_ABUSE_WARNING_TEXT=...       # свой текст предупреждения (необязательно)
    TRIAL_ABUSE_EXCLUDE_TELEGRAM_IDS=  # белый список TG id через запятую
    TRIAL_ABUSE_REPORT_MODE=always     # always | changes | never — отчёт админу в TG
"""

import asyncio
import html
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from aiogram import Bot
from sqlalchemy import select

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import Subscription, User
from app.external.remnawave_api import RemnaWaveUser, UserStatus
from app.services.remnawave_service import remnawave_service

logger = structlog.get_logger(__name__)


DEFAULT_WARNING_TEXT = (
    '⚠️ Обнаружено злоупотребление бесплатным триалом: с вашего устройства '
    'зарегистрировано несколько аккаунтов. Это нарушает правила сервиса.\n\n'
    'Если сервис вам нужен — оформите платную подписку, она недорогая. '
    'Спасибо за понимание!'
)

# Статусы подписок в БД бота, которые НЕ считаются реально взятым триалом/покупкой
_DRAFT_SUBSCRIPTION_STATUSES = {'pending'}
# Подписка считается «живой платной» в этих статусах
_ACTIVE_PAID_STATUSES = {'active', 'limited'}
# Мусорные HWID, которые встречаются у клиентских приложений
_BAD_HWIDS = {'', 'unknown', 'null', 'none', 'undefined', '(null)', 'default'}


class TrialAbuseService:
    """Периодическая проверка и наказание абузеров триалов."""

    def __init__(self) -> None:
        self.bot: Bot | None = None
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        # Антиспам: кого уже наказывали в рамках этого процесса
        self._punished: set[int] = set()

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    def start_task(self) -> None:
        """Запуск фоновой задачей. Ссылка хранится в синглтоне, чтобы
        event loop не собрал задачу сборщиком мусора."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.start())

    # ------------------------------------------------------------------ #
    # Настройки (читаются через getattr — сервис не падает, если поля
    # не добавлены в config.py; для загрузки из .env добавьте блок
    # полей в app/config.py — см. инструкцию по установке)
    # ------------------------------------------------------------------ #
    def is_enabled(self) -> bool:
        return bool(getattr(settings, 'TRIAL_ABUSE_ENABLED', False))

    def get_interval_hours(self) -> int:
        return max(1, int(getattr(settings, 'TRIAL_ABUSE_INTERVAL_HOURS', 4)))

    def get_action(self) -> str:
        action = str(getattr(settings, 'TRIAL_ABUSE_ACTION', 'expire')).strip().lower()
        return action if action in ('expire', 'disable') else 'expire'

    def is_notify_enabled(self) -> bool:
        return bool(getattr(settings, 'TRIAL_ABUSE_NOTIFY', True))

    def get_min_accounts(self) -> int:
        return max(2, int(getattr(settings, 'TRIAL_ABUSE_MIN_ACCOUNTS', 2)))

    def get_start_delay_seconds(self) -> int:
        return max(0, int(getattr(settings, 'TRIAL_ABUSE_START_DELAY_MINUTES', 5))) * 60

    def get_warning_text(self) -> str:
        text = str(getattr(settings, 'TRIAL_ABUSE_WARNING_TEXT', '') or '').strip()
        if not text:
            return DEFAULT_WARNING_TEXT
        # В .env переносы строк обычно записывают буквальным \n
        return text.replace('\\n', '\n')

    def get_report_mode(self) -> str:
        mode = str(getattr(settings, 'TRIAL_ABUSE_REPORT_MODE', 'always')).strip().lower()
        return mode if mode in ('always', 'changes', 'never') else 'always'

    def get_excluded_telegram_ids(self) -> set[int]:
        """Белый список: админы бота + TRIAL_ABUSE_EXCLUDE_TELEGRAM_IDS."""
        excluded: set[int] = set()
        raw_custom = str(getattr(settings, 'TRIAL_ABUSE_EXCLUDE_TELEGRAM_IDS', '') or '')
        raw_admin = getattr(settings, 'ADMIN_IDS', '') or ''
        for raw in (raw_custom, raw_admin if isinstance(raw_admin, str) else ''):
            for chunk in str(raw).replace(';', ',').split(','):
                chunk = chunk.strip()
                if chunk.lstrip('-').isdigit():
                    excluded.add(int(chunk))
        if isinstance(raw_admin, (list, tuple, set)):
            for item in raw_admin:
                try:
                    excluded.add(int(item))
                except (TypeError, ValueError):
                    continue
        return excluded

    # ------------------------------------------------------------------ #
    # Жизненный цикл
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if not self.is_enabled():
            logger.info('Антиабуз триалов: сервис отключён (TRIAL_ABUSE_ENABLED)')
            return
        if not remnawave_service.is_configured:
            logger.warning('Антиабуз триалов: RemnaWave API не настроен, сервис не запущен')
            return

        self._stop_event = asyncio.Event()
        interval = self.get_interval_hours() * 3600
        logger.info(
            f'Антиабуз триалов: запущен, интервал {self.get_interval_hours()}ч, '
            f'действие: {self.get_action()}, уведомления: {self.is_notify_enabled()}'
        )

        try:
            delay = self.get_start_delay_seconds()
            if delay:
                await asyncio.sleep(delay)
            while not self._stop_event.is_set():
                try:
                    stats = await self.run_check()
                    logger.info(f'Антиабуз триалов: проверка завершена: {stats}')
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.error(f'Антиабуз триалов: ошибка проверки: {error}', exc_info=True)
                    await self._notify_admin(
                        f'🛡 Антиабуз триалов: ошибка проверки: '
                        f'<code>{html.escape(str(error))}</code>'
                    )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.info('Антиабуз триалов: сервис остановлен')
            raise

    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------ #
    # Основная проверка
    # ------------------------------------------------------------------ #
    async def run_check(self) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        stats: dict[str, int] = defaultdict(int)

        async with remnawave_service.get_api_client() as api:
            devices_payload = await api.get_all_hwid_devices()
            if isinstance(devices_payload, dict):
                devices = devices_payload.get('devices') or []
            else:
                devices = []
            panel_users = await api.get_all_users_stream()

            users_by_id: dict[int, RemnaWaveUser] = {u.id: u for u in panel_users}
            stats['panel_users'] = len(users_by_id)
            stats['devices'] = len(devices)

            bot_index = await self._load_bot_index(now)

            # --- группировка устройств по HWID ---
            groups: dict[str, set[int]] = defaultdict(set)
            for device in devices:
                if not isinstance(device, dict):
                    continue
                hwid = str(device.get('hwid') or '').strip()
                raw_uid = device.get('userId')
                if raw_uid is None or not self._is_valid_hwid(hwid):
                    continue
                try:
                    uid = int(raw_uid)
                except (TypeError, ValueError):
                    continue
                if uid in users_by_id:
                    groups[hwid].add(uid)

            # candidates: panel_user_id -> причина
            candidates: dict[int, str] = {}
            min_accounts = self.get_min_accounts()

            for hwid, uids in groups.items():
                if len(uids) < min_accounts:
                    continue
                stats['hwid_groups'] += 1
                tg_ids = {
                    users_by_id[uid].telegram_id
                    for uid in uids
                    if users_by_id[uid].telegram_id
                }
                # Все аккаунты привязаны к одному Telegram — это один человек
                # (например, пересоздание подписки), не наказываем.
                if len(tg_ids) == 1:
                    stats['skipped_same_telegram'] += 1
                    continue
                for uid in uids:
                    verdict = self._account_verdict(users_by_id[uid], bot_index, now)
                    stats[f'verdict_{verdict}'] += 1
                    if verdict == 'candidate':
                        candidates[uid] = f'HWID …{hwid[-6:]} на {len(uids)} акк.'

            # --- мультитриал по данным БД бота (2+ триальных подписок) ---
            for record in bot_index['records'].values():
                if record['trial_count'] < min_accounts:
                    continue
                stats['multi_trial_users'] += 1
                for panel_id in record['panel_ids']:
                    panel_user = users_by_id.get(panel_id)
                    if panel_user is None:
                        continue
                    verdict = self._account_verdict(panel_user, bot_index, now)
                    stats[f'verdict_{verdict}'] += 1
                    if verdict == 'candidate':
                        candidates[panel_id] = (
                            f'{record["trial_count"]} триальных подписок в боте'
                        )

            # --- фильтры: белый список и антиспам ---
            excluded = self.get_excluded_telegram_ids()
            for panel_id in list(candidates):
                tg_id = users_by_id[panel_id].telegram_id
                if tg_id and tg_id in excluded:
                    del candidates[panel_id]
                    stats['skipped_whitelist'] += 1
                elif panel_id in self._punished:
                    del candidates[panel_id]
                    stats['skipped_already_punished'] += 1

            # --- применение ---
            punished_ok: list[str] = []
            punished_fail: list[str] = []
            for panel_id, reason in candidates.items():
                panel_user = users_by_id[panel_id]
                notified = False
                if self.is_notify_enabled() and panel_user.telegram_id and self.bot:
                    notified = await self._send_warning(panel_user.telegram_id)
                    stats['notified' if notified else 'notify_failed'] += 1

                ok, detail = await self._apply_action(api, panel_user)
                label = (
                    f'id={panel_id} @{html.escape(str(panel_user.username or "-"))} '
                    f'tg={panel_user.telegram_id or "-"} ({html.escape(reason)})'
                )
                if ok:
                    self._punished.add(panel_id)
                    punished_ok.append(label + (' 📨' if notified else ''))
                    stats['punished'] += 1
                    logger.warning(f'Антиабуз триалов: наказан {label} -> {detail}')
                else:
                    punished_fail.append(f'{label}: {html.escape(str(detail))}')
                    stats['errors'] += 1
                    logger.error(f'Антиабуз триалов: ошибка наказания {label}: {detail}')
                await asyncio.sleep(0.3)  # не долбим API панели

        report_mode = self.get_report_mode()
        should_report = report_mode == 'always' or (
            report_mode == 'changes' and (punished_ok or punished_fail)
        )
        if should_report:
            await self._send_admin_summary(stats, punished_ok, punished_fail)

        return dict(stats)

    # ------------------------------------------------------------------ #
    # Вердикты
    # ------------------------------------------------------------------ #
    def _account_verdict(
        self,
        panel_user: RemnaWaveUser,
        bot_index: dict[str, Any],
        now: datetime,
    ) -> str:
        """candidate | paid | unknown | already_disabled | already_expired."""
        record = bot_index['by_id'].get(panel_user.id)
        if record is None and panel_user.short_uuid:
            record = bot_index['by_short'].get(panel_user.short_uuid)
        if record is None and panel_user.telegram_id is not None:
            record = bot_index['by_tg'].get(panel_user.telegram_id)

        if panel_user.id in bot_index.get('paid_panel_ids', set()):
            return 'paid'  # panel id числится за платным — полный иммунитет
        if record is None:
            return 'unknown'  # нет связки с ботом — не трогаем никогда
        if record['paid_ever'] or record['paid_active']:
            return 'paid'  # платных не трогаем никогда
        if panel_user.status == UserStatus.DISABLED:
            return 'already_disabled'
        expire_at = self._as_utc(panel_user.expire_at)
        if panel_user.status == UserStatus.EXPIRED or (expire_at and expire_at <= now):
            return 'already_expired'  # не обнуляем вхолостую
        return 'candidate'

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _is_valid_hwid(hwid: str) -> bool:
        return len(hwid) >= 8 and hwid.lower() not in _BAD_HWIDS

    # ------------------------------------------------------------------ #
    # Индекс пользователей бота
    # ------------------------------------------------------------------ #
    async def _load_bot_index(self, now: datetime) -> dict[str, Any]:
        """Индекс БД бота для связки с панелью и платёжных проверок."""
        async with AsyncSessionLocal() as session:
            user_rows = (
                await session.execute(
                    select(
                        User.id,
                        User.telegram_id,
                        User.remnawave_id,
                        User.has_had_paid_subscription,
                    )
                )
            ).all()
            sub_rows = (
                await session.execute(
                    select(
                        Subscription.user_id,
                        Subscription.status,
                        Subscription.is_trial,
                        Subscription.end_date,
                        Subscription.remnawave_id,
                        Subscription.remnawave_short_uuid,
                    )
                )
            ).all()

        records: dict[int, dict[str, Any]] = {}
        for user_id, telegram_id, remnawave_id, has_had_paid in user_rows:
            panel_ids: set[int] = set()
            if remnawave_id is not None:
                try:
                    panel_ids.add(int(remnawave_id))
                except (TypeError, ValueError):
                    pass
            records[user_id] = {
                'telegram_id': telegram_id,
                'panel_ids': panel_ids,
                'shorts': set(),
                'paid_ever': bool(has_had_paid),
                'paid_active': False,
                'trial_count': 0,
            }

        for user_id, status, is_trial, end_date, sub_rw_id, sub_short in sub_rows:
            record = records.get(user_id)
            if record is None:
                continue
            status = str(status or '').lower()
            if status in _DRAFT_SUBSCRIPTION_STATUSES:
                continue  # неоплаченный черновик — не триал и не покупка
            if sub_rw_id is not None:
                try:
                    record['panel_ids'].add(int(sub_rw_id))
                except (TypeError, ValueError):
                    pass
            if sub_short:
                record['shorts'].add(str(sub_short))
            if is_trial:
                record['trial_count'] += 1
            else:
                record['paid_ever'] = True
                sub_end = self._as_utc(end_date)
                if status in _ACTIVE_PAID_STATUSES and sub_end and sub_end > now:
                    record['paid_active'] = True

        by_id: dict[int, dict[str, Any]] = {}
        by_short: dict[str, dict[str, Any]] = {}
        by_tg: dict[int, dict[str, Any]] = {}
        paid_panel_ids: set[int] = set()
        for record in records.values():
            for panel_id in record['panel_ids']:
                by_id.setdefault(panel_id, record)
            for short in record['shorts']:
                by_short.setdefault(short, record)
            if record['telegram_id'] is not None:
                by_tg.setdefault(int(record['telegram_id']), record)
            if record['paid_ever'] or record['paid_active']:
                paid_panel_ids.update(record['panel_ids'])

        return {
            'records': records,
            'by_id': by_id,
            'by_short': by_short,
            'by_tg': by_tg,
            'paid_panel_ids': paid_panel_ids,
        }

    # ------------------------------------------------------------------ #
    # Действия
    # ------------------------------------------------------------------ #
    async def _apply_action(self, api, panel_user: RemnaWaveUser) -> tuple[bool, str]:
        try:
            if self.get_action() == 'disable':
                await api.disable_user(panel_user.id)
                return True, 'disabled'
            # expire: панель 3.x отклоняет expireAt в прошлом (zod-валидация),
            # поэтому «обнуление» = истечение через 30 секунд.
            expire_at = datetime.now(timezone.utc) + timedelta(seconds=30)
            await api.update_user(panel_user.id, expire_at=expire_at)
            return True, 'expired'
        except Exception as error:
            return False, str(error)

    async def _send_warning(self, telegram_id: int) -> bool:
        if not self.bot:
            return False
        try:
            await self.bot.send_message(chat_id=telegram_id, text=self.get_warning_text())
            return True
        except Exception as error:
            logger.warning(
                f'Антиабуз триалов: не удалось отправить предупреждение '
                f'tg={telegram_id}: {error}'
            )
            return False

    # ------------------------------------------------------------------ #
    # Уведомления админу
    # ------------------------------------------------------------------ #
    async def _send_admin_summary(
        self,
        stats: dict[str, int],
        punished_ok: list[str],
        punished_fail: list[str],
    ) -> None:
        lines = [
            '🛡 <b>Антиабуз триалов: отчёт</b>',
            f'Пользователей в панели: {stats.get("panel_users", 0)}, '
            f'устройств: {stats.get("devices", 0)}',
            f'HWID-групп 2+: {stats.get("hwid_groups", 0)}, '
            f'мультитриалов: {stats.get("multi_trial_users", 0)}',
            f'Пропущено платных: {stats.get("verdict_paid", 0)}, '
            f'уже наказанных/истёкших: '
            f'{stats.get("verdict_already_disabled", 0) + stats.get("verdict_already_expired", 0)}',
        ]
        if punished_ok:
            lines.append(f'\n✅ Наказано ({self.get_action()}): {len(punished_ok)}')
            lines.extend(f'  • {item}' for item in punished_ok[:15])
            if len(punished_ok) > 15:
                lines.append(f'  … и ещё {len(punished_ok) - 15}')
        if punished_fail:
            lines.append(f'\n❌ Ошибок: {len(punished_fail)}')
            lines.extend(f'  • {item}' for item in punished_fail[:5])
        if not punished_ok and not punished_fail:
            lines.append('\n✅ Нарушителей не найдено, всё чисто.')
        await self._notify_admin('\n'.join(lines))

    async def _notify_admin(self, text: str) -> None:
        if not self.bot:
            return
        chat_id = getattr(settings, 'ADMIN_NOTIFICATIONS_CHAT_ID', None)
        if not chat_id:
            excluded = self.get_excluded_telegram_ids()
            chat_id = next(iter(excluded), None)
        if not chat_id:
            return
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        except Exception as error:
            logger.warning(f'Антиабуз триалов: не удалось уведомить админа: {error}')


trial_abuse_service = TrialAbuseService()
