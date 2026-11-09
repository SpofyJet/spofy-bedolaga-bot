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
    from app.cabinet.services.email_templates import EmailNotificationTemplates
    from app.cabinet.services.email_unsubscribe import build_unsubscribe_url
    from app.config import settings

    if not email or not settings.is_notifications_enabled() or not email_service.is_configured():
        return False

    subject, body, button, footer = render_reminder(
        kind, language, amount_kopeks=amount_kopeks, description=description, minutes=minutes
    )
    cabinet_url = (settings.CABINET_URL or '').rstrip('/')
    path = '/balance/top-up' if kind == 'payment' else '/subscription/purchase'
    # Оплата: сразу экран способов оплаты с той же суммой, без повторного ввода.
    query = f'?amount={(amount_kopeks + 99) // 100}' if kind == 'payment' and amount_kopeks > 0 else ''
    link = f'{cabinet_url}{path}{query}' if cabinet_url else ''
    unsubscribe_url = build_unsubscribe_url(user_id, email) if user_id else ''

    lang = (language or 'ru').split('-')[0].lower()
    body_html = EmailNotificationTemplates().render_simple_letter(
        language=lang if lang in _TEXTS else 'ru',
        title=subject,
        body_html=body,
        button_url=link,
        button_text=button,
        note=footer,
        unsubscribe_url=unsubscribe_url or '',
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
