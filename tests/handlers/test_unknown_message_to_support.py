"""Сообщение текстом вне сценария → одной кнопкой в поддержку."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers import common


def _state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=7, user_id=7))


def _user():
    return SimpleNamespace(id=42, language='ru')


def _message(text='не работает впн', photo=None):
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.photo = photo
    msg.answer = AsyncMock()
    return msg


def _buttons(markup):
    return [b.callback_data or b.url for row in markup.inline_keyboard for b in row]


async def test_text_message_offers_send_to_support():
    state = _state()
    msg = _message()
    await common.handle_unknown_message(msg, state, _user())
    text = msg.answer.await_args.args[0]
    markup = msg.answer.await_args.kwargs['reply_markup']
    assert 'поддержку' in text
    assert 'unknown_to_support' in _buttons(markup)
    assert 'back_to_menu' in _buttons(markup)
    data = await state.get_data()
    assert data[common._PENDING_SUPPORT_KEY]['text'] == 'не работает впн'
    assert await state.get_state() is None  # меню и кнопки продолжают работать


async def test_sticker_gets_no_send_button():
    state = _state()
    msg = _message(text=None)
    await common.handle_unknown_message(msg, state, _user())
    assert 'unknown_to_support' not in _buttons(msg.answer.await_args.kwargs['reply_markup'])


def _callback():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _db(active_ticket_id):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = active_ticket_id
    db.execute = AsyncMock(return_value=result)
    return db


async def test_creates_ticket_and_notifies_admins(monkeypatch):
    from app.database.crud import ticket as ticket_crud
    from app.handlers import tickets

    state = _state()
    await state.update_data(**{common._PENDING_SUPPORT_KEY: {'text': 'не работает впн\nна айфоне', 'photo': None}})
    created = SimpleNamespace(id=812)
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(ticket_crud.TicketCRUD, 'is_user_globally_blocked', AsyncMock(return_value=None))
    monkeypatch.setattr(ticket_crud.TicketCRUD, 'create_ticket', create)
    notify = AsyncMock()
    monkeypatch.setattr(tickets, 'notify_admins_about_new_ticket', notify)

    cb = _callback()
    await common.handle_unknown_to_support(cb, state, _user(), _db(None))

    assert create.await_args.args[2] == 'не работает впн'  # тема = первая строка
    assert create.await_args.args[3] == 'не работает впн\nна айфоне'
    notify.assert_awaited_once()
    assert '#812' in cb.message.edit_text.await_args.args[0]
    assert (await state.get_data())[common._PENDING_SUPPORT_KEY] is None


async def test_appends_to_open_ticket(monkeypatch):
    from app.database.crud import ticket as ticket_crud
    from app.handlers import tickets

    state = _state()
    await state.update_data(**{common._PENDING_SUPPORT_KEY: {'text': 'ещё вопрос', 'photo': None}})
    add = AsyncMock()
    monkeypatch.setattr(ticket_crud.TicketCRUD, 'is_user_globally_blocked', AsyncMock(return_value=None))
    monkeypatch.setattr(ticket_crud.TicketCRUD, 'create_ticket', AsyncMock(side_effect=AssertionError('не создавать')))
    monkeypatch.setattr(ticket_crud.TicketCRUD, 'get_ticket_by_id', AsyncMock(return_value=SimpleNamespace(id=55)))
    monkeypatch.setattr(ticket_crud.TicketMessageCRUD, 'add_message', add)
    notify = AsyncMock()
    monkeypatch.setattr(tickets, 'notify_admins_about_ticket_reply', notify)

    cb = _callback()
    await common.handle_unknown_to_support(cb, state, _user(), _db(55))

    assert add.await_args.args[1] == 55
    notify.assert_awaited_once()
    assert '#55' in cb.message.edit_text.await_args.args[0]


async def test_second_tap_does_not_duplicate(monkeypatch):
    state = _state()
    cb = _callback()
    await common.handle_unknown_to_support(cb, state, _user(), _db(None))
    assert cb.answer.await_args.kwargs.get('show_alert') is True
    cb.message.edit_text.assert_not_awaited()
