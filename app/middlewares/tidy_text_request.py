"""Единая «причёска» текста на выходе в Telegram: ни одно сообщение бота не уходит с рваными пустыми строками.

Работает на уровне запроса к API, поэтому покрывает всё сразу: ответы на кнопки, уведомления, рассылки, подписи
к баннеру. Сообщения с entities (кастомные эмодзи по смещениям) не трогаем: правка текста сдвинула бы смещения.
"""

from __future__ import annotations

from typing import Any

import structlog
from aiogram import Bot
from aiogram.client.default import Default
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import AnswerCallbackQuery, TelegramMethod

from app.utils.text_tidy import brand_bypass_sign, plain_alert_text, tidy_text


logger = structlog.get_logger(__name__)


class TidyTextRequestMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        try:
            self._tidy(method)
            self._brand(bot, method)
        except Exception:  # причёска не должна мешать отправке
            logger.debug('Не удалось причесать текст запроса', exc_info=True)
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

    @staticmethod
    def _is_html(bot: Bot, method: TelegramMethod[Any]) -> bool:
        parse_mode = getattr(method, 'parse_mode', None)
        if isinstance(parse_mode, Default):
            parse_mode = getattr(getattr(bot, 'default', None), 'parse_mode', None)
        return str(getattr(parse_mode, 'value', parse_mode) or '').upper() == 'HTML'

    @classmethod
    def _brand(cls, bot: Bot, method: TelegramMethod[Any]) -> None:
        """Знак обходов один на всех экранах: флаг из названия тарифа в базе → щит Spofy, как в локали и на кнопках."""
        if isinstance(method, AnswerCallbackQuery):
            return
        rich = getattr(method, 'rich_message', None)  # rich-сообщения: HTML лежит внутри InputRichMessage
        if rich is not None and isinstance(getattr(rich, 'html', None), str):
            branded = brand_bypass_sign(rich.html)
            if branded != rich.html:
                method.rich_message = rich.model_copy(update={'html': branded})
        media = getattr(method, 'media', None)
        if media is not None and isinstance(getattr(media, 'caption', None), str):
            media_mode = getattr(media, 'parse_mode', None)
            if isinstance(media_mode, Default):
                media_mode = getattr(getattr(bot, 'default', None), 'parse_mode', None)
            if (
                not getattr(media, 'caption_entities', None)
                and str(getattr(media_mode, 'value', media_mode) or '').upper() == 'HTML'
            ):
                branded = brand_bypass_sign(media.caption)
                if branded != media.caption:
                    method.media = media.model_copy(update={'caption': branded})
        if not cls._is_html(bot, method):
            return
        if isinstance(getattr(method, 'text', None), str) and not getattr(method, 'entities', None):
            method.text = brand_bypass_sign(method.text)
        if isinstance(getattr(method, 'caption', None), str) and not getattr(method, 'caption_entities', None):
            method.caption = brand_bypass_sign(method.caption)
