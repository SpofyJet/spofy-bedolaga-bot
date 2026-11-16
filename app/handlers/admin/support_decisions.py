from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import structlog
from aiogram import types
from aiogram.exceptions import TelegramBadRequest

from app.config import settings


logger = structlog.get_logger(__name__)

CALLBACK_PREFIX = 'supd'
DECISIONS_PATH = Path(os.getenv('SUPPORT_DECISIONS_PATH', 'data/support-decisions.jsonl'))

_LABELS = {'y': '✅ Да', 'n': '❌ Нет'}


def _admin_chat_id() -> int | None:
    raw = settings.ADMIN_NOTIFICATIONS_CHAT_ID
    try:
        return int(str(raw).strip()) if raw not in (None, '') else None
    except (TypeError, ValueError):
        return None


def parse_decision(data: str | None) -> tuple[int, str] | None:
    parts = (data or '').split(':')
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX or not parts[1].isdigit() or parts[2] not in _LABELS:
        return None
    return int(parts[1]), parts[2]


def is_support_decision(callback: types.CallbackQuery) -> bool:
    if parse_decision(callback.data) is None:
        return False
    chat_id = _admin_chat_id()
    message = callback.message
    return chat_id is not None and message is not None and message.chat.id == chat_id


async def handle_support_decision(callback: types.CallbackQuery) -> None:
    parsed = parse_decision(callback.data)
    if parsed is None:
        return
    ask_id, decision = parsed

    user = callback.from_user
    if user is None or not settings.is_admin(user.id):
        await callback.answer('Решение принимает только администратор', show_alert=True)
        return

    record = {
        'ask': ask_id,
        'decision': decision,
        'by': user.id,
        'ts': datetime.now(UTC).isoformat(timespec='seconds'),
    }
    try:
        DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DECISIONS_PATH.open('a', encoding='utf-8') as file:
            file.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError as error:
        logger.error('Не удалось записать решение по вопросу поддержки', ask_id=ask_id, error=str(error))
        await callback.answer('Не удалось записать решение, попробуйте ещё раз', show_alert=True)
        return

    label = _LABELS[decision]
    note = f'{label} — {user.first_name or "администратор"}' + (' · выполняю' if decision == 'y' else '')
    try:
        await callback.message.edit_text(f'{callback.message.text or ""}\n\n{note}', reply_markup=None, parse_mode=None)
    except TelegramBadRequest as error:
        logger.warning('Не удалось обновить сообщение с вопросом поддержки', ask_id=ask_id, error=str(error))
    await callback.answer(label)
    logger.info('Решение по вопросу поддержки записано', ask_id=ask_id, decision=decision, admin_id=user.id)
