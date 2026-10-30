"""Премиум-эмодзи-иконки на ВСЕХ кнопках бота — на уровне исходящего запроса.

Работает на уровне запроса к Bot API, поэтому покрывает всё сразу: клавиатуры
из билдеров, разметку, собранную на месте в хендлерах, рассылки, уведомления,
editMessageReplyMarkup. Сама карта «эмодзи → иконка» и логика очистки текста —
в app.keyboards.button_icons.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.keyboards.button_icons import apply_button_icons


class ButtonIconsMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        try:
            markup = getattr(method, 'reply_markup', None)
            if isinstance(markup, (InlineKeyboardMarkup, ReplyKeyboardMarkup)):
                apply_button_icons(markup)
        except Exception:  # иконка не должна мешать отправке
            pass
        return await make_request(bot, method)
