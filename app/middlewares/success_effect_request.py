"""Конфетти на сообщении об успешной оплате (эффект сообщения Telegram) в личном чате.

Сообщений об оплате много (десятки провайдеров), и у каждого свой код отправки. Поэтому эффект добавляется на выходе,
в запросе к API: по заголовку сообщения. Ничего не меняется в самом тексте и клавиатуре. Если Telegram отклонит
эффект (отключён, неверный id), сообщение уходит без него, и дальше эффект не шлётся до перезапуска.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage, TelegramMethod

from app.config import settings


logger = structlog.get_logger(__name__)

# Заголовки, зашитые в коде платёжных модулей (ru).
_HARDCODED_HEADINGS = (
    '✅ <b>Пополнение успешно!</b>',
    '✅ <b>Подписка успешно активирована!</b>',
    '🎉 <b>Платеж успешно обработан!</b>',
    '✅ <b>Платеж успешно завершен!</b>',
    '✅ <b>Оплата получена!</b>',
)
# Ключи локалей, чьи тексты — сообщения об успешной оплате/покупке; заголовок берётся на каждом языке.
_LOCALE_KEYS = (
    'PAYMENT_SUCCESS_CLOUDPAYMENTS',
    'STARS_PAYMENT_SUCCESS',
    'TARIFF_PURCHASE_SUCCESS',
    'TARIFF_RENEW_SUCCESS',
    'TARIFF_PURCHASE_DAILY_SUCCESS',
    'SUBSCRIPTION_PURCHASED',
)

_headings: tuple[str, ...] | None = None
_effect_unavailable = False


def _load_headings() -> tuple[str, ...]:
    global _headings
    if _headings is None:
        found = set(_HARDCODED_HEADINGS)
        locales = Path(__file__).resolve().parent.parent / 'localization' / 'locales'
        for path in locales.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            for key in _LOCALE_KEYS:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    found.add(value.strip().split('\n', 1)[0])
        _headings = tuple(sorted(found))
    return _headings


def is_success_message(text: str | None) -> bool:
    if not text:
        return False
    head = text.lstrip().split('\n', 1)[0]
    return any(head.startswith(h) or (h.startswith(head) and len(head) > 8) for h in _load_headings())


def _is_private_chat(chat_id: Any) -> bool:
    return isinstance(chat_id, int) and chat_id > 0


class SuccessEffectRequestMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        global _effect_unavailable
        effect = (getattr(settings, 'PAYMENT_SUCCESS_EFFECT_ID', '') or '').strip()
        if (
            not effect
            or _effect_unavailable
            or not isinstance(method, SendMessage)
            or method.message_effect_id
            or not _is_private_chat(method.chat_id)
            or not is_success_message(method.text)
        ):
            return await make_request(bot, method)
        method.message_effect_id = effect
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as error:
            if 'effect' not in str(error).lower():
                raise
            _effect_unavailable = True
            logger.warning('Telegram отклонил эффект сообщения: дальше без эффекта', error=str(error)[:160])
            method.message_effect_id = None
            return await make_request(bot, method)
