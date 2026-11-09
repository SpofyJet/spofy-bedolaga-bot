"""Ответ на обращение из админ-группы и /tickets."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.admin import ticket_group_reply as tgr


ADMIN_CHAT = -1001234567890
BOT_ID = 8021563068
ADMIN_ID = 111
STRANGER_ID = 222


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(tgr.settings, 'ADMIN_NOTIFICATIONS_CHAT_ID', str(ADMIN_CHAT), raising=False)
    monkeypatch.setattr(
        type(tgr.settings), 'is_admin', lambda self, telegram_id=None, email=None: telegram_id == ADMIN_ID
    )
    monkeypatch.setattr(type(tgr.settings), 'get_admin_ids', lambda self: [ADMIN_ID])
    monkeypatch.setattr(tgr.SupportSettingsService, 'is_moderator', classmethod(lambda cls, tid: False))


def _msg(
    *,
    chat_id=ADMIN_CHAT,
    sender=ADMIN_ID,
    sender_is_bot=False,
    reply_text=None,
    reply_from=BOT_ID,
    text='ответ',
    sender_chat=None,
):
    reply = None
    if reply_text is not None:
        reply = SimpleNamespace(text=reply_text, caption=None, from_user=SimpleNamespace(id=reply_from))
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        bot=SimpleNamespace(id=BOT_ID),
        from_user=SimpleNamespace(id=sender, is_bot=sender_is_bot),
        sender_chat=sender_chat,
        reply_to_message=reply,
        text=text,
        caption=None,
    )


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('🎫 Обращение #812 · новое\n👤 Анна', 812),
        ('💬 Обращение #77 · новое сообщение', 77),
        ('🎫 НОВЫЙ ТИКЕТ\n\n🆔 ID: 640\n👤 Пользователь: Анна\n🆔 ID: 512398771', 640),
        ('💬 ОТВЕТ НА ТИКЕТ\n\n🆔 ID тикета: 641\n🆔 ID: 512398771', 641),
        ('💰 Пополнение баланса 299 ₽', None),
    ],
)
def test_extract_ticket_id(text, expected):
    assert tgr.extract_ticket_id(SimpleNamespace(text=text, caption=None)) == expected


def test_admin_reply_to_ticket_card_is_accepted():
    assert tgr.is_admin_group_ticket_reply(_msg(reply_text='🎫 Обращение #5 · новое'))


@pytest.mark.parametrize(
    'kwargs',
    [
        {'sender': STRANGER_ID},  # не админ
        {'chat_id': -100999},  # другой чат
        {'reply_text': '🎫 Обращение #5', 'reply_from': 999},  # ответ не на сообщение бота
        {'reply_text': 'Пополнение 299 ₽'},  # не карточка обращения
        {'reply_text': None},  # не ответ вовсе
        {'sender': 555, 'sender_is_bot': True},  # другой бот
    ],
)
def test_other_group_messages_are_ignored(kwargs):
    base = {'reply_text': '🎫 Обращение #5 · новое'}
    base.update(kwargs)
    assert not tgr.is_admin_group_ticket_reply(_msg(**base))


def test_anonymous_group_admin_maps_to_first_admin():
    msg = _msg(
        sender=tgr._GROUP_ANONYMOUS_BOT_ID,
        sender_is_bot=True,
        sender_chat=SimpleNamespace(id=ADMIN_CHAT),
        reply_text='🎫 Обращение #5 · новое',
    )
    assert tgr._responder_telegram_id(msg) == ADMIN_ID
    assert tgr.is_admin_group_ticket_reply(msg)


def test_anonymous_bot_from_other_chat_is_rejected():
    msg = _msg(sender=tgr._GROUP_ANONYMOUS_BOT_ID, sender_is_bot=True, sender_chat=SimpleNamespace(id=-100555))
    assert tgr._responder_telegram_id(msg) is None


@pytest.mark.parametrize('text', ['/tickets', '/tickets@spofyvpnbot', '/обращения'])
def test_tickets_command_detected(text):
    assert tgr.is_admin_group_tickets_command(_msg(text=text))


def test_tickets_command_ignored_for_strangers():
    assert not tgr.is_admin_group_tickets_command(_msg(text='/tickets', sender=STRANGER_ID))


async def test_middleware_routes_admin_reply(monkeypatch):
    from aiogram.enums import ChatType
    from aiogram.types import Message

    from app.middlewares.chat_type_filter import ChatTypeFilterMiddleware

    handled = AsyncMock()
    monkeypatch.setattr(tgr, 'handle_admin_group_ticket_reply', handled)
    monkeypatch.setattr(tgr, 'is_admin_group_ticket_reply', lambda m: True)
    monkeypatch.setattr(tgr, 'is_admin_group_tickets_command', lambda m: False)

    event = Message.model_construct(chat=SimpleNamespace(id=ADMIN_CHAT, type=ChatType.SUPERGROUP))
    next_handler = AsyncMock()
    await ChatTypeFilterMiddleware()(next_handler, event, {})
    handled.assert_awaited_once()
    next_handler.assert_not_awaited()


async def test_middleware_still_drops_ordinary_group_messages(monkeypatch):
    from aiogram.enums import ChatType
    from aiogram.types import Message

    from app.middlewares.chat_type_filter import ChatTypeFilterMiddleware

    monkeypatch.setattr(tgr, 'is_admin_group_ticket_reply', lambda m: False)
    monkeypatch.setattr(tgr, 'is_admin_group_tickets_command', lambda m: False)
    event = Message.model_construct(chat=SimpleNamespace(id=ADMIN_CHAT, type=ChatType.SUPERGROUP))
    next_handler = AsyncMock()
    assert await ChatTypeFilterMiddleware()(next_handler, event, {}) is None
    next_handler.assert_not_awaited()


async def test_card_text_has_reply_marker_and_hint(monkeypatch):
    from app.handlers import tickets

    monkeypatch.setattr(tickets, '_ticket_card_subscription_line', AsyncMock(return_value='💳 Подписки нет'))
    ticket = SimpleNamespace(id=812, title='Не работает', updated_at=None, created_at=None)
    user = SimpleNamespace(id=1, full_name='Анна <b>', username='anna_k', telegram_id=512398771, email=None)
    text = await tickets.build_ticket_card_text(None, ticket, user, 'текст <script>', kind='new', in_group=True)
    assert text.startswith('🎫 <b>Обращение #812</b> · новое')
    assert tgr.extract_ticket_id(SimpleNamespace(text=text, caption=None)) == 812
    assert 'Анна &lt;b&gt;' in text and '&lt;script&gt;' in text
    assert 'Ответьте на это сообщение' in text
    private = await tickets.build_ticket_card_text(None, ticket, user, 'x', kind='reply', in_group=False)
    assert 'Ответьте на это сообщение' not in private
