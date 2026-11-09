from types import SimpleNamespace

from app.config import settings
from app.localization.texts import get_texts
from app.utils import notification_keyboards as nk
from app.utils.rich_admin import rich_footer_now


def test_keyboard_skips_missing_buttons(monkeypatch):
    monkeypatch.setattr(settings, 'SUPPORT_USERNAME', '')
    texts = get_texts('ru')
    markup = nk.keyboard(nk.support_button(texts), nk.buy_button(texts))
    assert markup is not None
    assert len(markup.inline_keyboard) == 1
    assert markup.inline_keyboard[0][0].style == 'success'


def test_keyboard_without_buttons_is_none():
    assert nk.keyboard(None) is None


def test_admin_links_need_cabinet_url(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', '')
    assert nk.admin_startup_keyboard() is None
    assert nk.admin_user_card_keyboard(SimpleNamespace(id=7)) is None


def test_admin_links_point_to_cabinet(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://cabinet.test/')
    card = nk.admin_user_card_keyboard(SimpleNamespace(id=7))
    assert card.inline_keyboard[0][0].url == 'https://cabinet.test/admin/users/7'
    urls = [button.url for row in nk.admin_startup_keyboard().inline_keyboard for button in row]
    assert urls[0] == 'https://cabinet.test/admin/dashboard'
    assert not any('github.com' in url or 't.me' in url for url in urls)


def test_admin_card_skips_missing_user(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://cabinet.test')
    assert nk.admin_user_card_keyboard(None) is None


def test_brand_in_footer():
    assert 'Spofy Bedolaga Bot' in rich_footer_now()
