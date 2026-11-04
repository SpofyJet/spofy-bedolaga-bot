"""«+1 спин в колесе призов» после пополнения.

Слушает событие payment.completed (его шлёт create_transaction для каждого DEPOSIT). Сам спин
никуда не начисляется: счёт выводится из транзакций (FortuneWheelService.get_free_spin_state),
здесь только сообщение, если это пополнение перешло порог очередного спина. Сообщение уходит
через пару секунд, после «✅ Зачислено», и никогда не мешает самому зачислению.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings


logger = structlog.get_logger(__name__)

NOTIFY_DELAY_SECONDS = 3.0

_bot: Bot | None = None
_registered = False
_tasks: set[asyncio.Task] = set()


def wheel_cabinet_url() -> str:
    base = (getattr(settings, 'CABINET_URL', '') or '').rstrip('/')
    if not base or 'example.com' in base:
        return ''
    return f'{base}/wheel'


def spins_earned(deposits_after_kopeks: int, amount_kopeks: int, threshold_kopeks: int) -> int:
    """Сколько новых спинов дало это пополнение (порог мог быть перейдён несколько раз)."""
    if threshold_kopeks <= 0 or amount_kopeks <= 0:
        return 0
    before = max(0, deposits_after_kopeks - amount_kopeks)
    return max(0, deposits_after_kopeks // threshold_kopeks - before // threshold_kopeks)


def build_spin_earned_message(
    language: str | None, earned: int, available: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    from app.localization.texts import get_texts

    texts = get_texts(language or 'ru')
    text = texts.t('WHEEL_TOPUP_SPIN_EARNED', '🎡 <b>+{earned} спин в колесе призов</b> — за пополнение.').format(
        earned=earned
    )
    text += '\n' + texts.t(
        'WHEEL_TOPUP_SPIN_PRIZES',
        'Можно выиграть дни, скидку, бонус на баланс или ещё одно устройство. Спинов: {available}.',
    ).format(available=available)
    url = wheel_cabinet_url()
    keyboard = None
    if url:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.t('WHEEL_TOPUP_SPIN_BUTTON', '🎡 Крутить колесо'), url=url, style='success'
                    )
                ]
            ]
        )
    return text, keyboard


async def _notify(user_id: int, amount_kopeks: int) -> None:
    await asyncio.sleep(NOTIFY_DELAY_SECONDS)
    from app.database.crud.wheel import get_topup_deposits_kopeks, get_wheel_config
    from app.database.database import AsyncSessionLocal
    from app.database.models import User
    from app.services.wheel_service import wheel_service

    async with AsyncSessionLocal() as db:
        config = await get_wheel_config(db)
        if config is None or not config.is_enabled or not config.topup_spins_enabled:
            return
        deposits = await get_topup_deposits_kopeks(db, user_id, config.topup_spins_since)
        earned = spins_earned(deposits, amount_kopeks, int(config.topup_spin_threshold_kopeks or 0))
        if earned <= 0:
            return
        user = await db.get(User, user_id)
        if user is None or not user.telegram_id or _bot is None:
            return
        free = await wheel_service.get_free_spin_state(db, user_id, config)
        text, keyboard = build_spin_earned_message(user.language, earned, max(free.available, earned))
        telegram_id = user.telegram_id
    try:
        await _bot.send_message(chat_id=telegram_id, text=text, parse_mode='HTML', reply_markup=keyboard)
    except Exception as error:
        logger.debug('Сообщение о спине колеса не доставлено', user_id=user_id, error=str(error))


async def on_payment_completed(event: dict[str, Any]) -> None:
    from app.database.crud.wheel import NON_TOPUP_PAYMENT_METHODS

    payload = event.get('payload') or {}
    method = payload.get('payment_method')
    user_id = payload.get('user_id')
    amount = int(payload.get('amount_kopeks') or 0)
    if not method or method in NON_TOPUP_PAYMENT_METHODS or not user_id or amount <= 0:
        return
    if payload.get('type') not in (None, 'deposit') or payload.get('is_completed') is False:
        return
    task = asyncio.create_task(_safe_notify(int(user_id), amount))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _safe_notify(user_id: int, amount_kopeks: int) -> None:
    try:
        await _notify(user_id, amount_kopeks)
    except Exception as error:
        logger.warning('Не удалось отправить сообщение о спине колеса', user_id=user_id, error=str(error))


def register_wheel_topup_notifier(bot: Bot | None) -> None:
    """Подключает слушатель к глобальному event_emitter (повторный вызов только обновляет бота)."""
    global _bot, _registered
    _bot = bot
    if _registered:
        return
    from app.services.event_emitter import event_emitter

    event_emitter.on('payment.completed', on_payment_completed)
    _registered = True
