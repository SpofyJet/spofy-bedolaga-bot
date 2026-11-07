"""/referral из меню команд открывает тот же экран, что кнопка «Пригласить друзей»."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.handlers import referral
from app.utils import bot_commands


def test_menu_has_only_start_and_referral():
    assert [c.command for c in bot_commands.COMMANDS['ru']] == ['start', 'referral']
    assert [c.command for c in bot_commands.COMMANDS['en']] == ['start', 'referral']


async def test_referral_command_sends_screen(monkeypatch):
    kb = MagicMock()
    monkeypatch.setattr(referral, '_referral_screen', AsyncMock(return_value=('экран друзей', kb)))
    msg = MagicMock()
    msg.answer = AsyncMock()
    await referral.cmd_referral(msg, SimpleNamespace(language='ru'), MagicMock())
    assert msg.answer.await_args.args[0] == 'экран друзей'
    assert msg.answer.await_args.kwargs['reply_markup'] is kb
