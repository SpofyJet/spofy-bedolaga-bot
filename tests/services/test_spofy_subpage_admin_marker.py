"""Spofy: покупки со страницы подписки отличаются в админ-чате.

Пока страница завершает свою корзину (и пока идёт уведомление о пополнении под
неё), к заголовку админ-уведомления дописывается «🔗 СТРАНИЦА ПОДПИСКИ»; с
ADMIN_NOTIFICATIONS_SUBPAGE_TOPIC_ID такие уведомления уходят в отдельный топик.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.services import spofy_subpage_context as ctx, spofy_subpage_service as completion
from app.services.admin_notification_service import AdminNotificationService


def test_mark_goes_to_the_title_line():
    text = '\n💎 <b>ПОКУПКА ПОДПИСКИ</b>\n\nПользователь: x'
    marked = ctx.mark_subpage_text(text)
    assert marked.startswith('\n💎 <b>ПОКУПКА ПОДПИСКИ</b> · 🔗 <b>СТРАНИЦА ПОДПИСКИ</b>\n')
    assert marked.endswith('Пользователь: x')
    assert ctx.mark_subpage_text(marked) == marked  # идемпотентно


def test_context_is_off_by_default_and_resets():
    assert not ctx.is_subpage_purchase_context()
    with ctx.subpage_purchase_context():
        assert ctx.is_subpage_purchase_context()
    assert not ctx.is_subpage_purchase_context()


def _service(monkeypatch):
    svc = AdminNotificationService(MagicMock())
    monkeypatch.setattr(svc, '_is_enabled', lambda: True)
    monkeypatch.setattr(svc, 'resolve_recipient_role', lambda: 'group')
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr('app.services.admin_notification_service.try_send_rich_admin_message', sent)
    monkeypatch.setattr('app.services.admin_notification_service.classic_admin_html_to_rich', lambda text, **kw: text)
    return svc, sent


async def test_send_message_marks_and_routes_subpage_purchases(monkeypatch):
    svc, sent = _service(monkeypatch)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_SUBPAGE_TOPIC_ID', 777)

    with ctx.subpage_purchase_context():
        await svc._send_message('💎 <b>ПОКУПКА ПОДПИСКИ</b>\nтело')

    text = sent.await_args.args[2]
    assert '🔗 <b>СТРАНИЦА ПОДПИСКИ</b>' in text.split('\n')[0]
    assert sent.await_args.kwargs['thread_id'] == 777


async def test_regular_purchases_are_untouched(monkeypatch):
    svc, sent = _service(monkeypatch)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_SUBPAGE_TOPIC_ID', 777)

    await svc._send_message('💎 <b>ПОКУПКА ПОДПИСКИ</b>\nтело')

    assert 'СТРАНИЦА ПОДПИСКИ' not in sent.await_args.args[2]
    assert sent.await_args.kwargs['thread_id'] != 777


async def test_cart_completion_runs_inside_the_context(monkeypatch):
    seen = []

    async def fake_process(db, user, cart, *, bot=None):
        seen.append(ctx.is_subpage_purchase_context())
        return True

    monkeypatch.setattr('app.services.subscription_auto_purchase_service._process_single_cart', fake_process)
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', False)
    cart = {'source': completion.SUBPAGE_SOURCE, 'subscription_id': 1}
    monkeypatch.setattr(completion.user_cart_service, 'get_all_subscription_carts', AsyncMock(return_value=[cart]))
    monkeypatch.setattr(completion.user_cart_service, 'get_user_cart', AsyncMock(return_value=None))
    monkeypatch.setattr(completion.user_cart_service, 'has_topup_intent', AsyncMock(return_value=True))
    monkeypatch.setattr(completion.user_cart_service, 'clear_topup_intent', AsyncMock())

    assert await completion.complete_subpage_carts_after_topup(MagicMock(), SimpleNamespace(id=5))
    assert seen == [True]
    assert not ctx.is_subpage_purchase_context()


async def test_topup_notification_is_marked_when_a_subpage_purchase_is_pending(monkeypatch):
    svc = AdminNotificationService(MagicMock())
    seen = []

    async def inner(user, *args, **kwargs):
        seen.append(ctx.is_subpage_purchase_context())
        return True

    monkeypatch.setattr(svc, '_send_balance_topup_notification', inner)

    monkeypatch.setattr(ctx, 'user_has_pending_subpage_purchase', AsyncMock(return_value=True))
    await svc.send_balance_topup_notification(SimpleNamespace(id=5), MagicMock(), 0)
    monkeypatch.setattr(ctx, 'user_has_pending_subpage_purchase', AsyncMock(return_value=False))
    await svc.send_balance_topup_notification(SimpleNamespace(id=5), MagicMock(), 0)

    assert seen == [True, False]
