"""Единая «причёска» текста на выходе в Telegram: ни одно сообщение бота не уходит с рваными пустыми строками.

Работает на уровне запроса к API, поэтому покрывает всё сразу: ответы на кнопки, уведомления, рассылки, подписи
к баннеру. Сообщения с entities (кастомные эмодзи по смещениям) не трогаем: правка текста сдвинула бы смещения.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import AnswerCallbackQuery, TelegramMethod

from app.utils.text_tidy import plain_alert_text, tidy_text


class TidyTextRequestMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        try:
            self._tidy(method)
        except Exception:  # причёска не должна мешать отправке
            pass
        return await make_request(bot, method)

    @staticmethod
    def _tidy(method: TelegramMethod[Any]) -> None:
        if isinstance(method, AnswerCallbackQuery):
            # Всплывающее окно и «тост» после нажатия — простой текст, без HTML: тексты из
            # локали с <tg-emoji …> и <b> показывались сырыми тегами («<tg-emoji emoji-id=…>✅…»).
            if isinstance(method.text, str):
                method.text = plain_alert_text(method.text)
            return
        if isinstance(getattr(method, 'text', None), str) and not getattr(method, 'entities', None):
            method.text = tidy_text(method.text)
        if isinstance(getattr(method, 'caption', None), str) and not getattr(method, 'caption_entities', None):
            method.caption = tidy_text(method.caption)
        media = getattr(method, 'media', None)  # EditMessageMedia: подпись внутри InputMedia
        if media is not None and isinstance(getattr(media, 'caption', None), str):
            if not getattr(media, 'caption_entities', None):
                # InputMedia заморожен: подменяем копией
                method.media = media.model_copy(update={'caption': tidy_text(media.caption)})
