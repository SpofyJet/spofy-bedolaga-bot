"""Копия Telegram-рассылки письмом тем, у кого нет Telegram.

Человек, вошедший в кабинет только по почте, Telegram-рассылку не видит:
у него нет telegram_id. Здесь та же рассылка (та же цель, аудитория и
категория) уходит ему письмом.

Почта — обычный SMTP с суточным пределом у почтовика (у Gmail ~500 писем в
сутки, и превышение блокирует отправку на сутки, включая коды входа). Поэтому
копии рассылок идут не быстрее ``_SEND_INTERVAL_SEC`` и не больше
``BROADCAST_EMAIL_MIRROR_DAILY_LIMIT`` писем за сутки UTC на все рассылки
вместе. Остаток ждёт следующих суток, а очередь лежит в файле и переживает
перезапуск бота.

В файле очереди — только id пользователей: адрес берётся из базы в момент
отправки (за сутки человек мог сменить или отвязать почту).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import html
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import BroadcastHistory, User
from app.services.broadcast_audience import BROADCAST_USER_STATUSES


if TYPE_CHECKING:
    from aiogram import Bot

    from app.cabinet.schemas.broadcasts import BroadcastAudience
    from app.cabinet.services.email_service import EmailService
    from app.services.broadcast_service import BroadcastConfig


logger = structlog.get_logger(__name__)


MIRROR_DIR = Path('data/broadcast_email_mirror')
DEFAULT_SUBJECT = 'Новости Spofy VPN'
SUBJECT_MAX_LENGTH = 90
CABINET_BUTTON_TEXT = 'Открыть личный кабинет'

_SEND_INTERVAL_SEC = 0.5  # не быстрее ~2 писем в секунду
_DB_CHUNK = 50
# Столько отказов подряд — это уже не адреса, а почтовик (обрыв, предел):
# возвращаем их в очередь и ждём, а не сжигаем очередь впустую.
_FAILURE_STREAK_LIMIT = 10
_FAILURE_STREAK_PAUSE_SEC = 30 * 60
_COUNTER_KEY_PREFIX = 'broadcast_email_mirror:sent:'
_COUNTER_TTL_SEC = 3 * 24 * 3600
_DAY_SEC = 24 * 3600

_ALLOWED_TAGS = frozenset({'b', 'i', 'u', 's', 'a', 'code', 'pre', 'blockquote'})
_TAG_ALIASES = {'strong': 'b', 'em': 'i', 'ins': 'u', 'strike': 's', 'del': 's'}
_SAFE_HREF_RE = re.compile(r'^(https?://|mailto:)', re.IGNORECASE)
_TG_EMOJI_RE = re.compile(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r'<[^<>]*>')


# ---------------------------------------------------------------------------
# Текст Telegram → HTML письма
# ---------------------------------------------------------------------------


class _TelegramToEmailHtml(HTMLParser):
    """Разрешённые теги Telegram остаются, tg-emoji и спойлер — просто текстом,
    прочие теги снимаются (их текст остаётся), переводы строк → <br>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._open: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = _TAG_ALIASES.get(tag.lower(), tag.lower())
        if tag not in _ALLOWED_TAGS:
            return
        if tag == 'a':
            href = (dict(attrs).get('href') or '').strip()
            if not _SAFE_HREF_RE.match(href):
                return
            self._parts.append(f'<a href="{html.escape(href, quote=True)}">')
        else:
            self._parts.append(f'<{tag}>')
        self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == 'br':
            self._parts.append('<br>')

    def handle_endtag(self, tag: str) -> None:
        tag = _TAG_ALIASES.get(tag.lower(), tag.lower())
        if tag not in self._open:
            return
        while self._open:
            closed = self._open.pop()
            self._parts.append(f'</{closed}>')
            if closed == tag:
                break

    def handle_data(self, data: str) -> None:
        escaped = html.escape(data, quote=False)
        if 'pre' not in self._open:
            escaped = escaped.replace('\r\n', '\n').replace('\n', '<br>\n')
        self._parts.append(escaped)

    def result(self) -> str:
        self.close()
        while self._open:
            self._parts.append(f'</{self._open.pop()}>')
        return ''.join(self._parts).strip()


def _unwrap_tg_emoji(text: str) -> str:
    return _TG_EMOJI_RE.sub(r'\1', text)


def telegram_html_to_email_html(text: str | None) -> str:
    """HTML сообщения Telegram → фрагмент HTML письма."""
    if not text:
        return ''
    parser = _TelegramToEmailHtml()
    parser.feed(_unwrap_tg_emoji(text))
    return parser.result()


def subject_from_telegram_text(text: str | None) -> str:
    """Тема письма: первая непустая строка без тегов, не длиннее 90 символов."""
    plain = html.unescape(_TAG_RE.sub('', _unwrap_tg_emoji(text or '')))
    for line in plain.splitlines():
        line = ' '.join(line.split())
        if line:
            if len(line) > SUBJECT_MAX_LENGTH:
                line = line[: SUBJECT_MAX_LENGTH - 1].rstrip() + '…'
            return line
    return DEFAULT_SUBJECT


def build_email_body(
    text: str | None,
    *,
    has_callback_buttons: bool,
    custom_buttons: Iterable[dict] | None = None,
) -> str:
    """Тело письма: текст и кнопки-ссылки.

    Кнопки бота (callback) в письме не нажать — вместо них одна ссылка на
    кабинет. Кнопки-ссылки из рассылки остаются ссылками.
    """
    parts: list[str] = []
    body = telegram_html_to_email_html(text)
    if body:
        parts.append(f'<div>{body}</div>')

    links: list[str] = []
    for button in custom_buttons or ():
        if button.get('action_type') != 'url':
            if button.get('label') and button.get('action_value'):
                has_callback_buttons = True
            continue
        label = _unwrap_tg_emoji(str(button.get('label') or '')).strip()
        href = str(button.get('action_value') or '').strip()
        if label and href.lower().startswith(('http://', 'https://')):
            links.append(
                f'<a class="button" href="{html.escape(href, quote=True)}">{html.escape(label, quote=False)}</a>'
            )

    cabinet_url = settings.normalized_cabinet_url()
    if has_callback_buttons and cabinet_url:
        links.insert(0, f'<a class="button" href="{html.escape(cabinet_url, quote=True)}">{CABINET_BUTTON_TEXT}</a>')

    parts.extend(f'<p style="margin: 16px 0;">{link}</p>' for link in links)
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Адресаты
# ---------------------------------------------------------------------------


def pick_mirror_user_ids(users: Iterable[User], category: str = 'system') -> list[int]:
    """Из тех же адресатов, что у Telegram-рассылки, — те, кому она не дойдёт:
    без telegram_id, с подтверждённой почтой, статус как у рассылок.
    Отписавшиеся от категории (news/promo) отсеиваются, как в почтовой рассылке."""
    from app.utils.notification_prefs import filter_users_by_broadcast_category

    candidates = [
        user
        for user in users
        if user.telegram_id is None and user.email and user.email_verified and user.status in BROADCAST_USER_STATUSES
    ]
    seen: set[int] = set()
    result: list[int] = []
    for user in filter_users_by_broadcast_category(candidates, category):
        if user.id not in seen:
            seen.add(user.id)
            result.append(user.id)
    return sorted(result)


async def fetch_mirror_user_ids(
    target: str, category: str = 'system', audience: BroadcastAudience | None = None
) -> list[int]:
    """Адресаты копии для рассылки по target/audience (без загрузки адресов в память)."""
    from app.handlers.admin.messages import get_custom_users, get_target_users
    from app.services.broadcast_audience import select_audience_users

    async with AsyncSessionLocal() as session:
        if audience is not None:
            # Канал email уже требует подтверждённую почту и статус рассылки.
            users = await select_audience_users(session, audience, 'email', category)
            return sorted({user.id for user in users if user.telegram_id is None and user.email})
        if target.startswith('custom_'):
            users = await get_custom_users(session, target[len('custom_') :])
        else:
            users = await get_target_users(session, target)
        return pick_mirror_user_ids(users, category)


def should_mirror(config: BroadcastConfig, *, resume: bool) -> bool:
    """Персональные отправки (промопредложения) и продолжение после перезапуска не копируются."""
    if resume:
        return False
    return config.recipient_ids is None and config.keyboard_factory is None


# ---------------------------------------------------------------------------
# Очередь
# ---------------------------------------------------------------------------


@dataclass
class MirrorJob:
    broadcast_id: int
    subject: str
    body_html: str
    category: str
    user_ids: list[int]
    attachment_path: str | None = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MirrorJob:
        return cls(
            broadcast_id=int(data['broadcast_id']),
            subject=str(data.get('subject') or DEFAULT_SUBJECT),
            body_html=str(data.get('body_html') or ''),
            category=str(data.get('category') or 'system'),
            user_ids=[int(i) for i in data.get('user_ids') or []],
            attachment_path=data.get('attachment_path') or None,
            total=int(data.get('total') or 0),
            sent=int(data.get('sent') or 0),
            failed=int(data.get('failed') or 0),
            created_at=str(data.get('created_at') or datetime.now(UTC).isoformat()),
        )


def _seconds_until_next_utc_day(now: datetime | None = None) -> float:
    # Сутки предела — UTC по договорённости (не календарный день сервиса): счётчик
    # в Redis ключуется датой UTC, и ждать надо до смены именно этой даты.
    timestamp = (now or datetime.now(UTC)).timestamp()
    return _DAY_SEC - timestamp % _DAY_SEC + 30


class DailyCounter:
    """Сколько писем-копий ушло за сутки UTC (общий счётчик всех рассылок).

    Живёт в Redis, чтобы перезапуск бота его не обнулял; без Redis — в памяти.
    """

    def __init__(self) -> None:
        self._memory: dict[str, int] = {}

    @staticmethod
    def _key(now: datetime | None = None) -> str:
        return _COUNTER_KEY_PREFIX + (now or datetime.now(UTC)).strftime('%Y-%m-%d')

    @staticmethod
    def _redis():
        from app.utils.cache import cache

        return cache.redis_client if getattr(cache, '_connected', False) else None

    async def try_reserve(self, limit: int) -> bool:
        key = self._key()
        client = self._redis()
        if client is not None:
            try:
                value = int(await client.incr(key))
                if value == 1:
                    await client.expire(key, _COUNTER_TTL_SEC)
                if value > limit:
                    await client.decr(key)
                    return False
                return True
            except Exception as error:
                logger.warning('Счётчик писем-копий в Redis недоступен, считаем в памяти', error=str(error))
        value = self._memory.get(key, 0)
        if value >= limit:
            return False
        self._memory[key] = value + 1
        return True


class BroadcastEmailMirror:
    def __init__(self, directory: Path = MIRROR_DIR) -> None:
        self._dir = directory
        self._bot: Bot | None = None
        self._email_service: EmailService | None = None
        self._tasks: dict[int, asyncio.Task] = {}
        self.counter = DailyCounter()
        self.send_interval = _SEND_INTERVAL_SEC

    def set_bot(self, bot: Bot) -> None:
        self._bot = bot

    def set_email_service(self, email_service: EmailService) -> None:
        self._email_service = email_service

    @staticmethod
    def enabled() -> bool:
        return bool(getattr(settings, 'BROADCAST_EMAIL_MIRROR_ENABLED', True))

    @staticmethod
    def daily_limit() -> int:
        return max(0, int(getattr(settings, 'BROADCAST_EMAIL_MIRROR_DAILY_LIMIT', 300) or 0))

    # --- файл очереди -----------------------------------------------------

    def _state_path(self, broadcast_id: int) -> Path:
        return self._dir / f'{broadcast_id}.json'

    def _save(self, job: MirrorJob) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._state_path(job.broadcast_id)
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)

    def _finish(self, job: MirrorJob) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._state_path(job.broadcast_id).unlink()
        if job.attachment_path:
            with contextlib.suppress(FileNotFoundError):
                Path(job.attachment_path).unlink()

    # --- запуск -----------------------------------------------------------

    async def start_from_config(self, broadcast_id: int, config: BroadcastConfig) -> int:
        """Копия рассылки из BroadcastService (кабинет и прочие запуски через сервис)."""
        try:
            # Канал email/both шлёт письма сам: адресатов незачем и выбирать.
            if await self._channel_has_email(broadcast_id):
                return 0
            user_ids = await fetch_mirror_user_ids(config.target, config.category, config.audience)
        except Exception:
            logger.exception('Копия рассылки письмом: не удалось выбрать адресатов', broadcast_id=broadcast_id)
            return 0
        media = config.media
        text = (media.caption or config.message_text) if media else config.message_text
        return await self.start(
            broadcast_id,
            user_ids=user_ids,
            message_text=text,
            media_type=media.type if media else None,
            media_file_id=media.file_id if media else None,
            has_callback_buttons=bool(config.selected_buttons),
            custom_buttons=config.custom_buttons,
            category=config.category,
        )

    async def start(
        self,
        broadcast_id: int,
        *,
        user_ids: list[int],
        message_text: str | None,
        media_type: str | None = None,
        media_file_id: str | None = None,
        has_callback_buttons: bool = False,
        custom_buttons: list[dict] | None = None,
        category: str = 'system',
    ) -> int:
        """Ставит копию в очередь и запускает её фоном. Возвращает число адресатов (0 — не запущена)."""
        if not self.enabled() or not user_ids:
            return 0
        if broadcast_id in self._tasks or self._state_path(broadcast_id).exists():
            return 0
        if self._email_service is None or not self._email_service.is_configured():
            logger.warning('Копия рассылки письмом не запущена: почта не настроена', broadcast_id=broadcast_id)
            return 0
        if await self._channel_has_email(broadcast_id):
            return 0

        attachment_path = None
        if media_type == 'photo' and media_file_id:
            attachment_path = await self._download_photo(broadcast_id, media_file_id)

        job = MirrorJob(
            broadcast_id=broadcast_id,
            subject=subject_from_telegram_text(message_text),
            body_html=build_email_body(
                message_text, has_callback_buttons=has_callback_buttons, custom_buttons=custom_buttons
            ),
            category=category or 'system',
            user_ids=list(user_ids),
            attachment_path=attachment_path,
            total=len(user_ids),
        )
        self._save(job)
        logger.info(
            'Копия рассылки письмом: старт',
            broadcast_id=broadcast_id,
            recipients=job.total,
            with_photo=bool(attachment_path),
            daily_limit=self.daily_limit(),
        )
        self._spawn(job)
        return job.total

    async def resume_pending(self) -> int:
        """При старте бота: продолжить очереди копий, которые оборвал перезапуск."""
        if not self.enabled() or not self._dir.exists():
            return 0
        resumed = 0
        for path in sorted(self._dir.glob('*.json')):
            try:
                job = MirrorJob.from_dict(json.loads(path.read_text(encoding='utf-8')))
            except Exception as error:
                logger.warning('Очередь копии рассылки не прочитана', file=path.name, error=str(error))
                continue
            if job.broadcast_id in self._tasks:
                continue
            if not job.user_ids:
                self._finish(job)
                continue
            logger.info(
                'Копия рассылки письмом: продолжаем после перезапуска',
                broadcast_id=job.broadcast_id,
                left=len(job.user_ids),
                sent=job.sent,
            )
            self._spawn(job)
            resumed += 1
        return resumed

    def _spawn(self, job: MirrorJob) -> None:
        from app.utils.background import spawn_background_task

        task = spawn_background_task(self._run(job), name=f'broadcast-email-mirror-{job.broadcast_id}')
        self._tasks[job.broadcast_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job.broadcast_id, None))

    @staticmethod
    async def _channel_has_email(broadcast_id: int) -> bool:
        """Рассылка с каналом email/both письма шлёт сама — копия не нужна."""
        async with AsyncSessionLocal() as session:
            record = await session.get(BroadcastHistory, broadcast_id)
            return bool(record and (record.channel or 'telegram') in ('email', 'both'))

    async def _download_photo(self, broadcast_id: int, file_id: str) -> str | None:
        if self._bot is None:
            return None
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f'{broadcast_id}.jpg'
        try:
            await self._bot.download(file_id, destination=path)
        except Exception as error:
            logger.warning('Копия рассылки письмом: фото не скачано, письмо уйдёт без него', error=str(error))
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            return None
        return str(path)

    # --- отправка ---------------------------------------------------------

    @staticmethod
    async def _load_recipients(user_ids: list[int]) -> dict[int, Any]:
        from app.services.broadcast_service import _EmailRecipient

        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(User.id, User.email, User.username, User.first_name, User.last_name, User.language).where(
                    User.id.in_(user_ids),
                    User.telegram_id.is_(None),
                    User.email.isnot(None),
                    User.email_verified.is_(True),
                    User.status.in_(BROADCAST_USER_STATUSES),
                )
            )
            recipients = {}
            for user_id, email, username, first_name, last_name, language in rows.all():
                name = username or ' '.join(filter(None, (first_name, last_name))) or email.split('@')[0]
                recipients[user_id] = _EmailRecipient(
                    email=email, user_name=name, user_id=user_id, language=language or 'ru'
                )
            return recipients

    def _send_one(self, job: MirrorJob, recipient: Any, attachment: tuple[str, bytes, str] | None) -> bool:
        from app.cabinet.services.email_unsubscribe import build_unsubscribe_url
        from app.services.broadcast_service import EmailBroadcastService

        unsubscribe_url = (
            build_unsubscribe_url(recipient.user_id, recipient.email) if job.category in ('news', 'promo') else ''
        )
        subject, body_html = EmailBroadcastService.render_email(job.subject, job.body_html, recipient, unsubscribe_url)
        return bool(
            self._email_service.send_email(
                to_email=recipient.email,
                subject=subject,
                body_html=body_html,
                attachments=[attachment] if attachment else None,
                unsubscribe_url=unsubscribe_url or None,
                queue_on_failure=False,
            )
        )

    def _read_attachment(self, job: MirrorJob) -> tuple[str, bytes, str] | None:
        if not job.attachment_path:
            return None
        try:
            return ('photo.jpg', Path(job.attachment_path).read_bytes(), 'image/jpeg')
        except OSError:
            return None

    def _log_summary(self, job: MirrorJob, message: str) -> None:
        logger.info(message, broadcast_id=job.broadcast_id, sent=job.sent, failed=job.failed, left=len(job.user_ids))

    async def _wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def _run(self, job: MirrorJob) -> None:
        attachment = self._read_attachment(job)
        loop = asyncio.get_running_loop()
        streak: list[int] = []
        try:
            while job.user_ids:
                chunk = job.user_ids[:_DB_CHUNK]
                recipients = await self._load_recipients(chunk)
                for user_id in chunk:
                    recipient = recipients.get(user_id)
                    if recipient is None:
                        # Человек отвязал почту, привязал Telegram или удалён — пропускаем.
                        job.user_ids.remove(user_id)
                        continue

                    if not await self.counter.try_reserve(self.daily_limit()):
                        self._save(job)
                        self._log_summary(job, 'Копия рассылки письмом: суточный предел, остаток завтра')
                        await self._wait(_seconds_until_next_utc_day())
                        break

                    try:
                        ok = await loop.run_in_executor(
                            None, functools.partial(self._send_one, job, recipient, attachment)
                        )
                    except Exception as error:
                        logger.warning(
                            'Копия рассылки письмом: ошибка отправки',
                            broadcast_id=job.broadcast_id,
                            user_id=user_id,
                            error=str(error)[:200],
                        )
                        ok = False

                    job.user_ids.remove(user_id)
                    if ok:
                        job.sent += 1
                        streak.clear()
                    else:
                        job.failed += 1
                        streak.append(user_id)
                    self._save(job)

                    if len(streak) >= _FAILURE_STREAK_LIMIT:
                        # Почтовик не принимает ничего — вернуть их в очередь и подождать.
                        job.user_ids[:0] = streak
                        job.failed -= len(streak)
                        streak.clear()
                        self._save(job)
                        self._log_summary(job, 'Копия рассылки письмом: отказы подряд, пауза 30 минут')
                        await self._wait(_FAILURE_STREAK_PAUSE_SEC)
                        break

                    await self._wait(self.send_interval)

            self._log_summary(job, 'Копия рассылки письмом: итог')
            self._finish(job)
        except asyncio.CancelledError:
            # Остановка бота: очередь уже в файле, продолжим при следующем старте.
            self._save(job)
            raise
        except Exception:
            logger.exception('Копия рассылки письмом оборвалась', broadcast_id=job.broadcast_id)
            self._save(job)


broadcast_email_mirror = BroadcastEmailMirror()
