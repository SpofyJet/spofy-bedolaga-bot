"""Ни одно сообщение бота не уходит с рваными пустыми строками."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.methods import EditMessageMedia, EditMessageText, SendMessage, SendPhoto
from aiogram.types import InputMediaPhoto, MessageEntity

from app.middlewares.tidy_text_request import TidyTextRequestMiddleware
from app.utils.text_tidy import tidy_text


def test_runs_of_blank_lines_collapse_to_one():
    assert tidy_text('a\n\n\n\nb') == 'a\n\nb'
    assert tidy_text('a\n \n\t\n\nb') == 'a\n\nb'
    assert tidy_text('a\n\nb') == 'a\n\nb'  # одна пустая строка — это нормальный абзац
    assert tidy_text('a\nb') == 'a\nb'


def test_edges_and_trailing_spaces_are_cleaned():
    assert tidy_text('\n\nпривет  \nмир\n\n') == 'привет\nмир'
    assert tidy_text(None) is None
    assert tidy_text('') == ''
    assert tidy_text('\n\n') == '\n\n'  # из одних переводов строки ничего не делаем: Telegram всё равно откажет


def test_the_devices_screen_from_the_complaint_is_fixed():
    broken = '📱 <b>Устройства</b>\n\nПодключено: <b>8 из 9</b>\n\n\n\n<b>Подключенные устройства:</b>\n• iOS\n\n\n✏️ — переименовать'
    fixed = tidy_text(broken)
    assert '\n\n\n' not in fixed
    assert 'Подключено: <b>8 из 9</b>\n\n<b>Подключенные' in fixed
    assert '• iOS\n\n✏️' in fixed


async def _run(method):
    make_request = AsyncMock(return_value='sent')
    await TidyTextRequestMiddleware()(make_request, MagicMock(), method)
    make_request.assert_awaited_once()
    return method


async def test_text_caption_and_media_caption_are_tidied():
    sent = await _run(SendMessage(chat_id=1, text='a\n\n\n\nb'))
    assert sent.text == 'a\n\nb'
    edited = await _run(EditMessageText(chat_id=1, message_id=2, text='x\n\n\n\ny'))
    assert edited.text == 'x\n\ny'
    photo = await _run(SendPhoto(chat_id=1, photo='file', caption='c\n\n\nd'))
    assert photo.caption == 'c\n\nd'
    media = await _run(EditMessageMedia(chat_id=1, message_id=2, media=InputMediaPhoto(media='f', caption='m\n\n\nn')))
    assert media.media.caption == 'm\n\nn'


async def test_messages_with_entities_are_left_alone():
    """Кастомные эмодзи задаются смещениями: правка текста их бы сдвинула."""
    entity = MessageEntity(type='bold', offset=0, length=1)
    sent = await _run(SendMessage(chat_id=1, text='a\n\n\n\nb', entities=[entity], parse_mode=None))
    assert sent.text == 'a\n\n\n\nb'


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_no_locale_template_has_more_than_one_blank_line_in_a_row(lang):
    import json
    import re
    from pathlib import Path

    data = json.loads(
        (Path(__file__).resolve().parent.parent / 'app/localization/locales' / f'{lang}.json').read_text()
    )
    bad = [
        key for key, value in data.items()
        if isinstance(value, str) and not key.startswith('ADMIN') and re.search(r'\\n[ \\t\\u00a0]*\\n[ \\t\\u00a0]*\\n', value)
    ]  # fmt: skip
    assert not bad, bad
