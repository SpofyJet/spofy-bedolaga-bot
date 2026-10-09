"""Письма-напоминания для аккаунтов без Telegram: брошенная оплата и брошенная корзина.

В Telegram такие напоминания приходят сообщением. У тех, кто сидит только в веб-кабинете (вход по email),
Telegram нет, поэтому то же самое уходит на подтверждённую почту, со ссылкой в кабинет и ссылкой отписки.
Принимает только скалярные значения (не ORM-объекты).
"""

from __future__ import annotations

import asyncio
import html

import structlog


logger = structlog.get_logger(__name__)

_TEXTS = {
    'ru': {
        'payment_subject': 'Оплата не завершена',
        'payment_body': 'Вы остановились на оплате <b>{amount} ₽</b>.<br><br>Не получилось оплатить? Попробуйте другой способ.',
        'payment_button': 'Продолжить оплату',
        'cart_subject': 'Вы остановились на покупке',
        'cart_body': '{description}<br>К оплате: <b>{amount} ₽</b>. Корзина сохранена ещё {minutes} мин: продолжите в один шаг.',
        'cart_button': 'Вернуться к оформлению',
        'footer': 'Это напоминание о вашем действии в кабинете.',
    },
    'en': {
        'payment_subject': 'Payment not completed',
        'payment_body': 'You stopped at a payment of <b>{amount} ₽</b>.<br><br>Could not pay? Try another method.',
        'payment_button': 'Continue payment',
        'cart_subject': 'You stopped at checkout',
        'cart_body': '{description}<br>To pay: <b>{amount} ₽</b>. Your cart is saved for another {minutes} min: finish in one step.',
        'cart_button': 'Back to checkout',
        'footer': 'This is a reminder about your action in the cabinet.',
    },
}


def render_reminder(kind: str, language: str | None, *, amount_kopeks: int, description: str = '', minutes: int = 20):
    """``(subject, html)`` письма: ``kind`` это ``payment`` или ``cart``."""
    texts = _TEXTS.get((language or 'ru').split('-')[0].lower(), _TEXTS['ru'])
    body = texts[f'{kind}_body'].format(
        amount=amount_kopeks // 100, description=html.escape(description or ''), minutes=minutes
    )
    return texts[f'{kind}_subject'], body, texts[f'{kind}_button'], texts['footer']


async def send_payment_reminder_email(
    *,
    email: str,
    language: str | None,
    user_id: int,
    kind: str,
    amount_kopeks: int,
    description: str = '',
    minutes: int = 20,
) -> bool:
    """Шлёт письмо-напоминание. True — письмо реально отправлено."""
    from app.cabinet.services.email_service import email_service
    from app.cabinet.services.email_unsubscribe import build_unsubscribe_url
    from app.config import settings

    if not email or not settings.is_notifications_enabled() or not email_service.is_configured():
        return False

    subject, body, button, footer = render_reminder(
        kind, language, amount_kopeks=amount_kopeks, description=description, minutes=minutes
    )
    cabinet_url = (getattr(settings, 'CABINET_URL', '') or '').rstrip('/')
    path = '/balance/top-up' if kind == 'payment' else '/subscription/purchase'
    link = f'{cabinet_url}{path}' if cabinet_url else ''
    unsubscribe_url = build_unsubscribe_url(user_id, email) if user_id else ''
    button_html = (
        f'<p style="margin:24px 0"><a href="{html.escape(link, quote=True)}" '
        'style="background:#2f80ed;color:#fff;padding:12px 22px;border-radius:10px;text-decoration:none;'
        f'font-weight:600">{html.escape(button)}</a></p>'
        if link
        else ''
    )
    body_html = (
        '<div style="font-family:Arial,sans-serif;font-size:16px;line-height:1.5;color:#1f2937">'
        f'<p>{body}</p>{button_html}<p style="color:#6b7280;font-size:13px">{html.escape(footer)}</p></div>'
    )
    try:
        # send_email: sync smtplib, в thread, чтобы не блокировать event loop
        sent = await asyncio.to_thread(
            email_service.send_email,
            to_email=email,
            subject=subject,
            body_html=body_html,
            body_text=None,
            unsubscribe_url=unsubscribe_url or None,
        )
    except Exception as error:
        logger.error('Ошибка отправки письма-напоминания', kind=kind, error=error)
        return False
    return bool(sent)
