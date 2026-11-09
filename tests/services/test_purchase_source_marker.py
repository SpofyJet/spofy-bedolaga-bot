"""Spofy: в админ-уведомлениях о покупках видно, откуда покупка — бот, кабинет или страница подписки."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.middlewares.context_binding import ContextVarsMiddleware
from app.services import spofy_subpage_context as ctx
from app.services.admin_notification_service import (
    AdminNotificationService,
    NotificationCategory,
)
from app.services.user_action_log_service import bind_request_path, reset_request_path


def test_source_is_unknown_by_default():
    assert ctx.current_purchase_source() is None


def test_explicit_source_and_subpage_flag():
    with ctx.purchase_source_context(ctx.SOURCE_BOT):
        assert ctx.current_purchase_source() == 'bot'
        with ctx.purchase_source_context(ctx.SOURCE_CABINET):
            assert ctx.current_purchase_source() == 'cabinet'
        with ctx.subpage_purchase_context():
            assert ctx.current_purchase_source() == 'subpage'
        assert ctx.current_purchase_source() == 'bot'
    assert ctx.current_purchase_source() is None


def test_cabinet_is_recognised_by_request_path():
    for path, expected in (
        ('/cabinet/subscription/purchase', 'cabinet'),
        ('/cabinet/spofy-subpage/abc/checkout', None),
        ('/cabinet/landing/x/purchase', None),
        ('/platega-webhook', None),
    ):
        token = bind_request_path(path)
        try:
            assert ctx.current_purchase_source() == expected, path
        finally:
            reset_request_path(token)


def test_cart_source():
    assert ctx.cart_purchase_source({'source': 'cabinet'}) == 'cabinet'
    assert ctx.cart_purchase_source({'source': 'spofy_subpage'}) == 'subpage'
    assert ctx.cart_purchase_source({'cart_mode': 'extend'}) == 'bot'
    assert ctx.cart_purchase_source(None) == 'bot'


def _service(monkeypatch):
    svc = AdminNotificationService(MagicMock())
    monkeypatch.setattr(svc, '_is_enabled', lambda: True)
    monkeypatch.setattr(svc, 'resolve_recipient_role', lambda: 'group')
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr('app.services.admin_notification_service.try_send_rich_admin_message', sent)
    monkeypatch.setattr('app.services.admin_notification_service.classic_admin_html_to_rich', lambda text, **kw: text)
    return svc, sent


async def test_purchase_from_bot_and_cabinet_is_marked(monkeypatch):
    svc, sent = _service(monkeypatch)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_SUBPAGE_TOPIC_ID', 777)

    with ctx.purchase_source_context(ctx.SOURCE_BOT):
        await svc._send_message('💎 <b>ПОКУПКА</b>\nтело', category=NotificationCategory.PURCHASES)
    assert sent.await_args.args[2].split('\n')[0] == '💎 <b>ПОКУПКА</b> · 🤖 <b>БОТ</b>'

    with ctx.purchase_source_context(ctx.SOURCE_CABINET):
        await svc._send_message('💎 <b>ПРОДЛЕНИЕ</b>\nтело', category=NotificationCategory.RENEWALS)
    assert sent.await_args.args[2].split('\n')[0] == '💎 <b>ПРОДЛЕНИЕ</b> · 🖥 <b>КАБИНЕТ</b>'
    assert sent.await_args.kwargs['thread_id'] != 777


async def test_other_categories_and_unknown_source_are_untouched(monkeypatch):
    svc, sent = _service(monkeypatch)

    with ctx.purchase_source_context(ctx.SOURCE_BOT):
        await svc._send_message('🎫 <b>ОБРАЩЕНИЕ</b>\nтело', category=NotificationCategory.TICKETS)
    assert 'БОТ' not in sent.await_args.args[2]

    await svc._send_message('💎 <b>АВТОПРОДЛЕНИЕ</b>\nтело', category=NotificationCategory.RENEWALS)
    assert '·' not in sent.await_args.args[2]


async def test_subpage_cart_routes_to_subpage_topic(monkeypatch):
    svc, sent = _service(monkeypatch)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_SUBPAGE_TOPIC_ID', 777)

    with ctx.purchase_source_context(ctx.cart_purchase_source({'source': 'spofy_subpage'})):
        await svc._send_message('💎 <b>ПОКУПКА</b>\nтело', category=NotificationCategory.PURCHASES)
    assert 'СТРАНИЦА ПОДПИСКИ' in sent.await_args.args[2].split('\n')[0]
    assert sent.await_args.kwargs['thread_id'] == 777


async def test_bot_middleware_sets_bot_source():
    seen = []

    async def handler(event, data):
        seen.append(ctx.current_purchase_source())

    event = SimpleNamespace(from_user=SimpleNamespace(id=1, username='u'), chat=SimpleNamespace(id=1))
    await ContextVarsMiddleware()(handler, event, {})
    assert seen == ['bot']
    assert ctx.current_purchase_source() is None


async def test_auto_purchase_after_topup_uses_cart_source(monkeypatch):
    from app.services import subscription_auto_purchase_service as auto

    seen = []

    async def fake_process(db, user, cart, *, bot=None, manual=False, bound_price_kopeks=None):
        seen.append(ctx.current_purchase_source())
        return True

    carts = [
        {'cart_mode': 'extend', 'subscription_id': 1, 'source': 'cabinet'},
        {'cart_mode': 'extend', 'subscription_id': 2},
    ]
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True)
    monkeypatch.setattr(auto, '_process_single_cart', fake_process)
    monkeypatch.setattr(auto.user_cart_service, 'get_user_cart', AsyncMock(return_value=None))
    monkeypatch.setattr(auto.user_cart_service, 'get_all_subscription_carts', AsyncMock(return_value=carts))
    monkeypatch.setattr(auto.user_cart_service, 'has_topup_intent', AsyncMock(return_value=True))

    assert (
        await auto.auto_purchase_saved_cart_after_topup(
            AsyncMock(), SimpleNamespace(id=5, telegram_id=5005, email=None), bot=None
        )
        is True
    )
    assert seen == ['cabinet', 'bot']
