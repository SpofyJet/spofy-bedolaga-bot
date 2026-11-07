"""Меню команд бота («/» в поле ввода).

Без этого Telegram показывал оставшееся от шаблона «🚀 Start bot» на английском.
Ставим при каждом старте: так меню не расходится с кодом.
"""

import structlog
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats


logger = structlog.get_logger(__name__)

COMMANDS = {
    'ru': [
        BotCommand(command='start', description='Главное меню'),
        BotCommand(command='referral', description='Пригласить друзей'),
    ],
    'en': [
        BotCommand(command='start', description='Main menu'),
        BotCommand(command='referral', description='Invite friends'),
    ],
}


async def configure_bot_commands(bot: Bot) -> None:
    scope = BotCommandScopeAllPrivateChats()
    try:
        # Русский — по умолчанию для всех, английский — для английского интерфейса Telegram.
        await bot.set_my_commands(COMMANDS['ru'], scope=scope)
        await bot.set_my_commands(COMMANDS['en'], scope=scope, language_code='en')
    except Exception as error:
        logger.warning('Не удалось обновить меню команд', error=error)
