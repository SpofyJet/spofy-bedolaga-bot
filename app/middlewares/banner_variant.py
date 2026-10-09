"""Баннер по состоянию человека: выбираем картинку один раз на обновление.

Новый человек видит «2 дня бесплатно», на пробном периоде — напоминание оформить подписку, платный подписчик —
«Подписка активна», тот, у кого доступ кончился, — «Доступ закончился». Сами картинки лежат в banners/,
а выбор подхватывает get_logo_media() через контекст обновления (см. app/utils/message_patch.py).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.utils.message_patch import reset_banner_variant, set_banner_variant


def banner_variant_for(user: Any) -> str | None:
    """Имя файла баннера (без .png) для человека; ``None`` — нужен общий баннер."""
    if user is None:
        return None
    try:
        subscriptions = list(getattr(user, 'subscriptions', None) or [])
        language = (getattr(user, 'language', None) or 'ru').split('-')[0].lower()
        active = [s for s in subscriptions if getattr(s, 'is_active', False)]
    except Exception:  # связь не загружена или объект отсоединён: баннер не должен ронять ответ
        return None
    if any(not getattr(s, 'is_trial', False) for s in active):
        state = 'paid'
    elif active:
        state = 'trial'
    elif subscriptions:
        state = 'expired'
    else:
        state = 'new'
    return state if language == 'ru' else f'{state}_{language}'


class BannerVariantMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        token = set_banner_variant(banner_variant_for(data.get('db_user')))
        try:
            return await handler(event, data)
        finally:
            reset_banner_variant(token)
