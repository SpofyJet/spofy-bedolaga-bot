"""Оповещение админов: деньги от провайдера пришли, а штатно применить их не вышло.

Логгеры ``app.payments`` / ``app.services.payment`` намеренно не уходят в
Telegram-лог (иначе чат тонет в шуме обычных ретраев), поэтому такие места
раньше были видны только в логах контейнера. Этот хелпер зовут ровно в
точках «оплата получена, но не зачислена/не выдана» — там, где без человека
деньги либо зависнут, либо уже ушли пользователю на баланс вместо услуги.

Никогда не бросает исключение: вызывающий — обработчик вебхука, и сбой
отправки в Telegram не должен менять ответ провайдеру.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any

from aiogram import Bot

from app.config import settings

# payments.log, а не общий логгер: иначе Telegram-лог-хендлер продублировал бы
# это же событие в чат вторым сообщением.
from app.utils.payment_logger import payment_logger as logger


def build_payment_problem_text(
    *,
    provider: str,
    problem: str,
    user_id: int | None,
    amount_kopeks: int | None,
    reference: str | None,
    details: Mapping[str, Any] | None,
) -> str:
    amount = f'{amount_kopeks / 100:.2f} ₽' if amount_kopeks is not None else '—'
    lines = [
        '🚨 <b>Платёж требует проверки</b>',
        '',
        f'<b>{html.escape(problem)}</b>',
        '',
        f'Провайдер: {html.escape(provider)}',
        f'Пользователь: {user_id if user_id is not None else "—"}',
        f'Сумма: {amount}',
    ]
    if reference:
        lines.append(f'ID: <code>{html.escape(str(reference))}</code>')
    for label, value in (details or {}).items():
        if value is None or value == '':
            continue
        lines.append(f'{html.escape(str(label))}: {html.escape(str(value))}')
    return '\n'.join(lines)


async def alert_payment_not_applied(
    bot: Bot | None,
    *,
    provider: str,
    problem: str,
    user_id: int | None = None,
    amount_kopeks: int | None = None,
    reference: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Лог уровня error + сообщение в админ-чат (топик ошибок).

    ``bot`` — экземпляр бота вызывающего, если он есть; без него (вебхук гостевой
    покупки, фоновые проверки) бот создаётся на одно сообщение, как в
    ``guest_purchase_service``.
    """
    logger.error(
        'Платёж получен, но не применён штатно',
        provider=provider,
        problem=problem,
        user_id=user_id,
        amount_kopeks=amount_kopeks,
        reference=reference,
        details=dict(details or {}),
    )
    try:
        text = build_payment_problem_text(
            provider=provider,
            problem=problem,
            user_id=user_id,
            amount_kopeks=amount_kopeks,
            reference=reference,
            details=details,
        )
        from app.services.admin_notification_service import AdminNotificationService, NotificationCategory

        if bot is not None:
            await AdminNotificationService(bot).send_admin_notification(text, category=NotificationCategory.ERRORS)
            return
        if not getattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False) or not settings.BOT_TOKEN:
            return
        from app.bot_factory import create_bot

        async with create_bot() as own_bot:
            await AdminNotificationService(own_bot).send_admin_notification(text, category=NotificationCategory.ERRORS)
    except Exception:
        logger.exception('Не удалось отправить админам оповещение о платеже', provider=provider, reference=reference)
