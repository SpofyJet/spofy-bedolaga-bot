"""Политика и оферта в боте: общий показ документа и общие проверки меню."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers import menu


class _Callback:
    def __init__(self, data: str | None = None):
        self.data = data
        self.answer = AsyncMock()
        self.edits: list[tuple[str, dict]] = []
        self.message = SimpleNamespace(edit_text=self._edit_text)

    async def _edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def _user():
    return SimpleNamespace(id=1, telegram_id=1, language='ru')


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


@pytest.fixture
def visible(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, 'PRIVACY_POLICY_DISPLAY_MODE', 'both')
    monkeypatch.setattr(settings, 'PUBLIC_OFFER_DISPLAY_MODE', 'both')
    return settings


@pytest.mark.asyncio
async def test_missing_user_gets_alert_and_no_screen():
    callback = _Callback('menu_privacy_policy')
    await menu.show_privacy_policy(callback, None, db=AsyncMock())
    callback.answer.assert_awaited_once_with('Ошибка: пользователь не найден.', show_alert=True)
    assert callback.edits == []


@pytest.mark.asyncio
async def test_hidden_section_is_not_loaded(monkeypatch, visible):
    monkeypatch.setattr(visible, 'PUBLIC_OFFER_DISPLAY_MODE', 'web')
    loader = AsyncMock()
    monkeypatch.setattr(menu.PublicOfferService, 'get_active_offer', loader)
    callback = _Callback('menu_public_offer')
    await menu.show_public_offer(callback, _user(), db=AsyncMock())
    callback.answer.assert_awaited_once_with('Раздел временно недоступен.', show_alert=True)
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_document_alert(monkeypatch, visible):
    monkeypatch.setattr(menu.PrivacyPolicyService, 'get_active_policy', AsyncMock(return_value=None))
    callback = _Callback('menu_privacy_policy')
    await menu.show_privacy_policy(callback, _user(), db=AsyncMock())
    callback.answer.assert_awaited_once_with('Политика конфиденциальности временно недоступна.', show_alert=True)


@pytest.mark.asyncio
async def test_long_offer_pages_with_own_callbacks(monkeypatch, visible):
    content = 'Пункт оферты. ' * 600
    monkeypatch.setattr(
        menu.PublicOfferService, 'get_active_offer', AsyncMock(return_value=SimpleNamespace(content=content))
    )
    callback = _Callback('menu_public_offer:2')
    await menu.show_public_offer(callback, _user(), db=AsyncMock())

    text, kwargs = callback.edits[0]
    assert '<b>Публичная оферта</b>\n\n' in text
    callbacks = _callbacks(kwargs['reply_markup'])
    assert callbacks[0] == 'menu_public_offer:1'
    assert callbacks[1] == 'noop'
    assert callbacks[-1] == 'menu_info'


@pytest.mark.parametrize(
    ('data', 'page'),
    [(None, 1), ('menu_rules', 1), ('menu_rules:3', 3), ('menu_rules:0', 1), ('menu_rules:x', 1)],
)
def test_callback_page_number(data, page):
    assert menu._callback_page_number(SimpleNamespace(data=data)) == page
