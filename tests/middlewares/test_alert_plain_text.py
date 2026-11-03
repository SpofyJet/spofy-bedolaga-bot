"""Всплывающие окна после нажатия кнопки — простой текст: теги из локали не видны человеку."""

import pytest
from aiogram.methods import AnswerCallbackQuery, SendMessage

from app.localization.texts import get_texts
from app.middlewares.tidy_text_request import TidyTextRequestMiddleware
from app.utils.text_tidy import ALERT_TEXT_LIMIT, plain_alert_text


def test_custom_emoji_tag_becomes_plain_emoji():
    raw = "<tg-emoji emoji-id='5776375003280838798'>✅</tg-emoji> Спасибо за подписку"
    assert plain_alert_text(raw) == '✅ Спасибо за подписку'


def test_html_tags_and_entities_are_removed():
    assert plain_alert_text('<b>Скидка</b> 10% &amp; <i>бонус</i> 2 &lt; 3') == 'Скидка 10% & бонус 2 < 3'


def test_long_text_is_cut_to_telegram_limit():
    assert len(plain_alert_text('я' * 300)) == ALERT_TEXT_LIMIT


def test_plain_text_is_untouched():
    assert plain_alert_text('Готово') == 'Готово'


@pytest.mark.parametrize('key', ['CHANNEL_SUBSCRIBE_THANKS', 'AUTOPAY_TOGGLE_SUCCESS', 'SUBSCRIPTION_NOT_FOUND'])
def test_locale_alerts_have_no_tags_after_tidy(key):
    method = AnswerCallbackQuery(callback_query_id='1', text=get_texts('ru').t(key, ''), show_alert=True)
    TidyTextRequestMiddleware._tidy(method)
    assert '<' not in method.text and 'tg-emoji' not in method.text


def test_regular_messages_keep_html():
    method = SendMessage(chat_id=1, text="<tg-emoji emoji-id='1'>✅</tg-emoji> <b>Оплачено</b>")
    TidyTextRequestMiddleware._tidy(method)
    assert '<b>' in method.text and 'tg-emoji' in method.text
