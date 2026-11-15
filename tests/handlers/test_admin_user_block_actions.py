"""Админка, карточка пользователя: подтверждение и итог удаления/блокировки/разблокировки."""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.admin import users


class _Callback:
    def __init__(self, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=1)
        self.answer = AsyncMock()
        self.edits: list[tuple[str, list]] = []
        self.message = SimpleNamespace(edit_text=self._edit_text)

    async def _edit_text(self, text, reply_markup=None, **_):
        rows = [[(b.text, b.callback_data) for b in row] for row in reply_markup.inline_keyboard]
        self.edits.append((text, rows))


ADMIN = SimpleNamespace(id=9, language='ru')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('handler', 'action'),
    [('confirm_user_delete', 'delete'), ('confirm_user_block', 'block'), ('confirm_user_unblock', 'unblock')],
)
async def test_confirm_screens_lead_to_action_and_back(handler, action):
    callback = _Callback(f'admin_user_{action}_42')
    await inspect.unwrap(getattr(users, handler))(callback, ADMIN)

    ((_, rows),) = callback.edits
    callbacks = [data for row in rows for _, data in row]
    assert callbacks == [f'admin_user_{action}_confirm_42', 'admin_user_manage_42']
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('handler', 'method', 'ok', 'fail'),
    [
        ('block_user', 'block_user', '✅ Пользователь заблокирован', '❌ Ошибка блокировки пользователя'),
        ('unblock_user', 'unblock_user', '✅ Пользователь разблокирован', '❌ Ошибка разблокировки пользователя'),
    ],
)
@pytest.mark.parametrize('success', [True, False])
async def test_block_result_has_back_to_user(monkeypatch, handler, method, ok, fail, success):
    service = SimpleNamespace(**{method: AsyncMock(return_value=success)})
    monkeypatch.setattr(users, 'UserService', lambda: service)
    callback = _Callback(f'admin_user_{method.split("_")[0]}_confirm_42')

    await inspect.unwrap(getattr(users, handler))(callback, ADMIN, db='db')

    assert callback.edits == [(ok if success else fail, [[('👤 К пользователю', 'admin_user_manage_42')]])]
    callback.answer.assert_awaited_once_with()
