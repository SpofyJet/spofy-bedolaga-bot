"""/paysupport: Telegram requires bots that sell for Stars to answer it (Bot Developer Terms 6.2.1)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User as TgUser

from app.config import settings
from app.handlers import support
from app.utils.support_access import is_payment_support_handler


def _message(chat_type='private', is_bot=False):
    msg = Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat.model_construct(id=7, type=chat_type),
        from_user=TgUser.model_construct(id=7, is_bot=is_bot, first_name='x', language_code='ru'),
        text='/paysupport',
    )
    object.__setattr__(msg, 'answer', AsyncMock())
    return msg


def _flagged(flag=True):
    return {'handler': SimpleNamespace(flags={'public_payment_support': flag})}


def test_bypass_only_for_the_flagged_private_handler():
    assert is_payment_support_handler(_message(), _flagged())
    assert not is_payment_support_handler(_message(), _flagged(False))
    assert not is_payment_support_handler(_message(), {'handler': SimpleNamespace(flags={})})
    assert not is_payment_support_handler(_message(), {})
    assert not is_payment_support_handler(_message(chat_type='group'), _flagged())
    assert not is_payment_support_handler(_message(is_bot=True), _flagged())


@pytest.fixture
def _support(monkeypatch):
    monkeypatch.setattr(type(settings), 'get_support_contact_url', lambda self: 'https://t.me/spofysup')
    monkeypatch.setattr(support.SupportSettingsService, 'is_tickets_enabled', classmethod(lambda cls: True))
    monkeypatch.setattr(
        support.SupportSettingsService, 'get_support_info_text', classmethod(lambda cls, lang: 'SUPPORT')
    )


def _buttons(msg):
    markup = msg.answer.await_args.kwargs['reply_markup']
    return [b for row in markup.inline_keyboard for b in row] if markup else []


async def test_active_user_gets_ticket_buttons_and_contact(_support):
    msg = _message()
    await support.payment_support_command(msg, SimpleNamespace(language='ru', status='active'))
    text = msg.answer.await_args.args[0]
    assert 'Помощь с оплатой' in text
    buttons = _buttons(msg)
    assert [b.callback_data for b in buttons[:2]] == ['create_ticket', 'my_tickets']
    assert buttons[-1].url == 'https://t.me/spofysup'


async def test_unknown_or_blocked_payer_still_gets_a_contact(_support):
    for db_user in (None, SimpleNamespace(language='ru', status='blocked')):
        msg = _message()
        await support.payment_support_command(msg, db_user)
        buttons = _buttons(msg)
        assert [b.url for b in buttons] == ['https://t.me/spofysup']


async def test_no_contact_and_no_tickets_falls_back_to_support_text(monkeypatch, _support):
    monkeypatch.setattr(type(settings), 'get_support_contact_url', lambda self: None)
    msg = _message()
    await support.payment_support_command(msg, None)
    assert msg.answer.await_args.args[0].endswith('SUPPORT')
    assert msg.answer.await_args.kwargs['reply_markup'] is None


def test_registered_first_with_the_flag():
    from aiogram import Dispatcher

    dp = Dispatcher()
    support.register_command_handlers(dp)
    [handler] = dp.message.handlers
    assert handler.flags.get('public_payment_support') is True
