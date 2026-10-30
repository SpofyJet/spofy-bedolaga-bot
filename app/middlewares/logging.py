import re
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


logger = structlog.get_logger(__name__)

# Длинные токены (webauth_<token>, GIFT_<код>, купоны) — это учётные данные: кто
# читает лог, успевает войти по чужому webauth или забрать подарок. Номера карт
# в реквизитах вывода — персональные данные.
# Заглавная буква + цифра отличают случайный токен от имён callback (menu_balance_back).
_SECRET_TOKEN_RE = re.compile(r'(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{20,}')
_CARD_NUMBER_RE = re.compile(r'\d(?:[ -]?\d){11,18}')


def _redact(value: str | None) -> str | None:
    if not value:
        return value
    value = _SECRET_TOKEN_RE.sub(lambda m: m.group(0)[:6] + '…', value)
    return _CARD_NUMBER_RE.sub('[номер скрыт]', value)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        start_time = monotonic()

        try:
            if isinstance(event, Message) and event.from_user:
                user_info = f'@{event.from_user.username}' if event.from_user.username else f'ID:{event.from_user.id}'
                text = event.text or event.caption or '[медиа]'
                logger.info('📩 Входящее сообщение', user_info=user_info, text=_redact(text))

            elif isinstance(event, CallbackQuery) and event.from_user:
                user_info = f'@{event.from_user.username}' if event.from_user.username else f'ID:{event.from_user.id}'
                logger.info('🔘 Входящий callback', user_info=user_info, event_data=_redact(event.data))

            result = await handler(event, data)

            execution_time = monotonic() - start_time
            if execution_time > 1.0:
                logger.warning('⏱️ Медленная операция', execution_time=round(execution_time, 2))

            return result

        except Exception as e:
            execution_time = monotonic() - start_time
            logger.exception('❌ Ошибка при обработке события', execution_time=round(execution_time, 2), error=e)
            raise
