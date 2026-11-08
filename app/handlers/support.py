import structlog
from aiogram import Dispatcher, F, types
from aiogram.filters import Command

from app.config import settings
from app.database.models import User
from app.keyboards.inline import get_support_keyboard
from app.localization.texts import get_texts
from app.services.support_settings_service import SupportSettingsService
from app.utils.photo_message import edit_or_answer_photo


logger = structlog.get_logger(__name__)


async def show_support_info(callback: types.CallbackQuery, db_user: User):
    get_texts(db_user.language)
    support_info = SupportSettingsService.get_support_info_text(db_user.language)
    await edit_or_answer_photo(
        callback=callback,
        caption=support_info,
        keyboard=get_support_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_support_info, F.data == 'menu_support')


async def payment_support_command(message: types.Message, db_user: User | None = None):
    """/paysupport — required of bots that sell for Telegram Stars (Bot Developer Terms 6.2.1).

    Reached past maintenance, blacklist, channel and name gates: whoever paid can always ask."""
    language = db_user.language if db_user else (message.from_user.language_code or settings.DEFAULT_LANGUAGE)
    texts = get_texts(language)
    rows: list[list[types.InlineKeyboardButton]] = []
    if db_user and db_user.status == 'active' and SupportSettingsService.is_tickets_enabled():
        rows.append([types.InlineKeyboardButton(text=texts.t('CREATE_TICKET_BUTTON'), callback_data='create_ticket')])
        rows.append([types.InlineKeyboardButton(text=texts.t('MY_TICKETS_BUTTON'), callback_data='my_tickets')])
    contact = settings.get_support_contact_url()
    if contact:
        rows.append([types.InlineKeyboardButton(text=texts.t('CONTACT_SUPPORT_BUTTON'), url=contact)])
    text = texts.t(
        'PAYMENT_SUPPORT_INFO',
        '<b>Помощь с оплатой</b>\n\nДеньги списались, а баланс или подписка не пополнились, или нужен возврат — '
        'напишите нам: дата, сумма и способ оплаты.',
    )
    if not rows:
        text += '\n\n' + SupportSettingsService.get_support_info_text(language)
    await message.answer(
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        parse_mode='HTML',
    )


def register_command_handlers(dp: Dispatcher):
    # before every other handler: a person stuck in some input step still gets an answer
    dp.message.register(
        payment_support_command,
        Command('paysupport'),
        F.chat.type == 'private',
        flags={'public_payment_support': True},
    )
