import json
import math
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from aiogram.exceptions import TelegramAPIError, TelegramNotFound
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, WidgetQuery

from app.config import settings
from app.database.crud.user import get_user_by_telegram_id
from app.database.database import AsyncSessionLocal
from app.services.bypass_downgrade import has_bypass, has_bypass_quota, is_suspension_effective
from app.services.referral_balance import get_referral_balance
from app.utils.legacy_subscription import is_legacy_subscription
from app.utils.lifetime import is_lifetime_end
from app.utils.message_patch import caption_exceeds_telegram_limit


logger = structlog.get_logger(__name__)

_DIR = Path(__file__).parent
_TEMPLATE = (_DIR / 'subscription_widget.html').read_text(encoding='utf-8')
_STRINGS = json.loads((_DIR / 'subscription_widget.json').read_text(encoding='utf-8'))
CARD_HTML = {
    lang: _TEMPLATE.replace('__L__', json.dumps(strings, ensure_ascii=False, separators=(',', ':')))
    for lang, strings in _STRINGS.items()
}
DATA_LIMIT = 1024
REFRESH = 'r'

NOT_ALLOWED_RETRY = 3600

_paused_until = 0.0


def widget_enabled() -> bool:
    return bool(settings.SUBSCRIPTION_WIDGET_ENABLED) and time.monotonic() >= _paused_until


def card_html(language: str | None) -> str:
    return CARD_HTML.get((language or 'ru')[:2], CARD_HTML['ru'])


def card_state(subscription: Any, now: datetime) -> str | None:
    status = subscription.status
    if status == 'limited':
        return 'a'
    if status in ('expired', 'disabled') or subscription.end_date <= now:
        return 'x'
    if status == 'active':
        return 'a'
    return None


def card_data(
    user: Any,
    subscription: Any,
    *,
    tariff: Any,
    devices: int | None,
    from_friends_kopeks: int,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    state = card_state(subscription, now or datetime.now(UTC))
    if state is None:
        return None
    trial = bool(subscription.is_trial)
    lifetime = is_lifetime_end(subscription.end_date)
    needs_tariff = is_legacy_subscription(subscription)
    daily = bool(getattr(tariff, 'is_daily', False))
    data: dict[str, Any] = {
        'v': 1,
        's': state,
        'e': int(subscription.end_date.timestamp()),
        'tr': trial,
        'lt': lifetime,
        'li': subscription.status == 'limited',
        'dl': subscription.device_limit or 0,
        'tu': round(float(subscription.traffic_used_gb or 0), 2),
        'tl': subscription.traffic_limit_gb or 0,
        'bq': has_bypass_quota(subscription),
        'bs': is_suspension_effective(subscription),
        'bx': bool(settings.BYPASS_SQUAD_UUID)
        and not has_bypass(subscription)
        and not (trial or lifetime or daily or needs_tariff),
        'nt': needs_tariff,
        'n': getattr(tariff, 'name', None),
        'b': math.floor((user.balance_kopeks or 0) / 100),
        'f': math.floor(max(0, from_friends_kopeks) / 100),
    }
    if devices is not None:
        data['dc'] = devices
    return data


def encode_card_data(data: dict[str, Any]) -> str:
    data = dict(data)
    while True:
        encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        overflow = len(encoded.encode()) - DATA_LIMIT
        if overflow <= 0:
            return encoded
        name = data.get('n') or ''
        if not name:
            raise ValueError('данные карточки длиннее 1024 байт')
        raw = name.encode()
        data['n'] = raw[: max(0, len(raw) - overflow)].decode(errors='ignore').rstrip() or None


def _pause_for(error: TelegramAPIError) -> float:
    text = str(error).lower()
    if isinstance(error, TelegramNotFound) or 'method not found' in text or 'unknown method' in text:
        return math.inf
    if 'widget_not_allowed' in text:
        return NOT_ALLOWED_RETRY
    return 0.0


async def try_send_subscription_widget(
    callback: CallbackQuery,
    *,
    language: str | None,
    data: dict[str, Any] | None,
    caption_parts: list[str],
    keyboard: InlineKeyboardMarkup,
) -> bool:
    global _paused_until
    message = callback.message
    chat = getattr(message, 'chat', None)
    if data is None or not widget_enabled() or chat is None or chat.type != 'private':
        return False
    parts = [
        part.strip().replace('\n</blockquote>', '</blockquote>') for part in caption_parts if part and part.strip()
    ]
    caption = '\n\n'.join(parts)
    if caption_exceeds_telegram_limit(caption):
        return False
    try:
        await callback.bot.send_widget(
            chat_id=chat.id,
            html=card_html(language),
            chat_data=encode_card_data(data),
            caption=caption or None,
            parse_mode='HTML' if caption else None,
            reply_markup=keyboard,
            allow_queries=True,
        )
    except TelegramAPIError as error:
        pause = _pause_for(error)
        if pause:
            _paused_until = time.monotonic() + pause
        logger.warning('Карточка подписки не отправлена, показан обычный экран', error=str(error))
        return False
    with suppress(TelegramAPIError):
        await message.delete()
    return True


async def _fresh_card_data(telegram_id: int) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_telegram_id(db, telegram_id)
        if user is None:
            return None
        subscription = user.subscription
        if subscription is None:
            return {'v': 1, 's': 'n', 'b': math.floor((user.balance_kopeks or 0) / 100)}
        tariff = getattr(subscription, 'tariff', None)
        if getattr(tariff, 'is_daily', False):
            return None
        balance = await get_referral_balance(db, user)
        return card_data(user, subscription, tariff=tariff, devices=None, from_friends_kopeks=balance.available_kopeks)


async def handle_subscription_widget_query(query: WidgetQuery) -> None:
    data = None
    chat = query.chat
    if (
        settings.SUBSCRIPTION_WIDGET_ENABLED
        and query.data == REFRESH
        and chat is not None
        and chat.type == 'private'
        and chat.id == query.from_user.id
    ):
        try:
            data = await _fresh_card_data(query.from_user.id)
        except Exception as error:
            logger.warning('Карточка подписки: не удалось собрать свежие данные', error=str(error))
    try:
        await query.answer(data=encode_card_data(data) if data else None)
    except TelegramAPIError as error:
        logger.debug('Карточка подписки: ответ не принят', error=str(error))
