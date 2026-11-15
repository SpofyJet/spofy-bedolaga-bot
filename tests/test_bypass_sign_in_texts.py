"""Знак обходов один на всех экранах: флаг из названия тарифа в базе уходит щитом Spofy, как в локали и на кнопках."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.methods import AnswerCallbackQuery, EditMessageMedia, EditMessageText, SendMessage, SendPhoto
from aiogram.types import InputMediaPhoto, InputRichMessage, MessageEntity

from app.keyboards.button_icons import BUTTON_ICONS
from app.middlewares.tidy_text_request import TidyTextRequestMiddleware
from app.utils.text_tidy import BYPASS_SIGN_EMOJI_ID, brand_bypass_sign


FLAG = '🏴‍☠️'
SHIELD = f"<tg-emoji emoji-id='{BYPASS_SIGN_EMOJI_ID}'>{FLAG}</tg-emoji>"
HTML_BOT = SimpleNamespace(default=SimpleNamespace(parse_mode='HTML'))


def test_sign_is_the_same_as_on_buttons():
    assert BUTTON_ICONS[FLAG] == BYPASS_SIGN_EMOJI_ID


def test_bare_flag_becomes_shield_and_wrapped_one_is_left_alone():
    assert brand_bypass_sign(f'<b>{FLAG} С Обходами</b> — 310 ₽') == f'<b>{SHIELD} С Обходами</b> — 310 ₽'
    assert brand_bypass_sign(f'{SHIELD} Обходы: 1 / 50 ГБ') == f'{SHIELD} Обходы: 1 / 50 ГБ'
    assert brand_bypass_sign(f'{SHIELD} и {FLAG}') == f'{SHIELD} и {SHIELD}'
    assert brand_bypass_sign('🏴‍☠ без селектора') == (
        f"<tg-emoji emoji-id='{BYPASS_SIGN_EMOJI_ID}'>🏴‍☠</tg-emoji> без селектора"
    )
    assert brand_bypass_sign(f'<code>{FLAG} С Обходами</code>') == f'<code>{FLAG} С Обходами</code>'
    assert brand_bypass_sign('⭐ Стандартный') == '⭐ Стандартный'
    assert brand_bypass_sign(None) is None


async def _run(method, bot=HTML_BOT):
    make_request = AsyncMock(return_value='sent')
    await TidyTextRequestMiddleware()(make_request, bot, method)
    make_request.assert_awaited_once()
    return method


async def test_text_caption_media_and_rich_message_get_the_shield():
    assert (await _run(SendMessage(chat_id=1, text=f'{FLAG} С Обходами'))).text == f'{SHIELD} С Обходами'
    assert (await _run(SendPhoto(chat_id=1, photo='f', caption=f'{FLAG} x'))).caption == f'{SHIELD} x'
    media = await _run(EditMessageMedia(chat_id=1, message_id=2, media=InputMediaPhoto(media='f', caption=f'{FLAG} x')))
    assert media.media.caption == f'{SHIELD} x'
    rich = await _run(
        EditMessageText(chat_id=1, message_id=2, text='', rich_message=InputRichMessage(html=f'<p>{FLAG} x</p>'))
    )
    assert rich.rich_message.html == f'<p>{SHIELD} x</p>'


async def test_non_html_messages_and_alerts_are_left_alone():
    assert (await _run(SendMessage(chat_id=1, text=f'{FLAG} x', parse_mode=None))).text == f'{FLAG} x'
    assert (await _run(SendMessage(chat_id=1, text=f'{FLAG} x', parse_mode='MarkdownV2'))).text == f'{FLAG} x'
    entity = MessageEntity(type='bold', offset=0, length=1)
    sent = await _run(SendMessage(chat_id=1, text=f'{FLAG} x', entities=[entity], parse_mode=None))
    assert sent.text == f'{FLAG} x'
    plain_bot = SimpleNamespace(default=SimpleNamespace(parse_mode=None))
    assert (await _run(SendMessage(chat_id=1, text=f'{FLAG} x'), plain_bot)).text == f'{FLAG} x'
    alert = await _run(AnswerCallbackQuery(callback_query_id='1', text=f'{FLAG} x'))
    assert alert.text == f'{FLAG} x'
