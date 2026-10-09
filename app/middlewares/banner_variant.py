"""Баннер по состоянию человека: выбираем картинку один раз на обновление.

Новый человек видит «2 дня бесплатно», на пробном периоде — напоминание оформить подписку, платный подписчик —
«Подписка активна», тот, у кого доступ кончился, — «Доступ закончился». Сами картинки лежат в banners/,
а выбор подхватывает get_logo_media() через контекст обновления (см. app/utils/message_patch.py).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from app.utils.message_patch import (
    reset_banner_text_only,
    reset_banner_variant,
    set_banner_text_only,
    set_banner_variant,
)


# Экраны без баннера: на них человек делает дело (устройства, приглашения, оплата), а картинка только
# уводит кнопки вниз. Баннер остаётся на главной, подписке и остальных экранах.
TEXT_ONLY_CALLBACK_PREFIXES = (
    # устройства
    'subscription_manage_devices',
    'subscription_change_devices',
    'devices_page',
    'reset_device',
    'reset_all_devices',
    'device_rename',
    'change_devices',
    'confirm_change_devices',
    # рефералы
    'menu_referrals',
    'referral_',
    # баланс и оплата
    'menu_balance',
    'balance_',
    'topup_',
    'check_',
)
TEXT_ONLY_STATE_PREFIXES = ('BalanceStates:', 'ReferralWithdrawalStates:')


def is_text_only_screen(callback_data: str | None, state_name: str | None) -> bool:
    if callback_data and callback_data.startswith(TEXT_ONLY_CALLBACK_PREFIXES):
        return True
    return bool(state_name and state_name.startswith(TEXT_ONLY_STATE_PREFIXES))


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
        callback_data = event.data if isinstance(event, CallbackQuery) else None
        state_name = None
        state = data.get('state')
        if state is not None:
            try:
                state_name = await state.get_state()
            except Exception:  # хранилище состояний недоступно — баннер не повод падать
                state_name = None
        token = set_banner_variant(banner_variant_for(data.get('db_user')))
        text_token = set_banner_text_only(is_text_only_screen(callback_data, state_name))
        try:
            return await handler(event, data)
        finally:
            reset_banner_text_only(text_token)
            reset_banner_variant(token)
