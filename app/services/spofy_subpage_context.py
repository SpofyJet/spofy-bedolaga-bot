"""Spofy: пометка «покупка со страницы подписки» для админ-уведомлений.

Покупки со страницы подписки (sub.spofyltd.ru) проходят обычным путём бота —
пополнение, потом завершение корзины, — и админ-уведомления о них ничем не
отличались от покупок в боте или кабинете. Пока страница завершает свою корзину
(или пока идёт уведомление о пополнении под эту корзину), в контексте стоит
флаг; общий отправитель админ-уведомлений по нему дописывает к заголовку
«🔗 СТРАНИЦА ПОДПИСКИ» и, если задан ADMIN_NOTIFICATIONS_SUBPAGE_TOPIC_ID, шлёт в
отдельный топик.

ContextVar, а не параметр: уведомления шлются глубоко внутри автопокупки, и
протаскивать «источник» через все её функции — большой хрупкий дифф. Задачи,
созданные внутри (asyncio.create_task), наследуют контекст.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


SUBPAGE_MARK = '🔗 <b>СТРАНИЦА ПОДПИСКИ</b>'

_subpage_purchase: ContextVar[bool] = ContextVar('spofy_subpage_purchase', default=False)


def is_subpage_purchase_context() -> bool:
    return _subpage_purchase.get()


@contextmanager
def subpage_purchase_context(active: bool = True) -> Iterator[None]:
    token = _subpage_purchase.set(active)
    try:
        yield
    finally:
        _subpage_purchase.reset(token)


def mark_subpage_text(text: str) -> str:
    """Дописать пометку к первой строке — заголовку уведомления (в rich-виде это h6)."""
    if SUBPAGE_MARK in text:
        return text
    leading = text[: len(text) - len(text.lstrip('\n'))]
    body = text.lstrip('\n')
    title, sep, rest = body.partition('\n')
    return f'{leading}{title} · {SUBPAGE_MARK}{sep}{rest}'


async def user_has_pending_subpage_purchase(user_id: int) -> bool:
    """Есть корзина страницы подписки и свежая метка пополнения под неё —
    то же условие, при котором её завершит complete_subpage_carts_after_topup."""
    from app.services.spofy_subpage_service import is_subpage_cart
    from app.services.user_cart_service import user_cart_service

    try:
        carts = list(await user_cart_service.get_all_subscription_carts(user_id))
        carts.append(await user_cart_service.get_user_cart(user_id))
        if not any(is_subpage_cart(cart) for cart in carts):
            return False
        return bool(await user_cart_service.has_topup_intent(user_id))
    except Exception:
        return False
