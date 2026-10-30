"""Оповещение админов: уже оплаченный платёж получил статус возврата/чарджбэка.

Зачисление на баланс при этом автоматически не откатывается — деньги могли быть
уже потрачены, и решение (списать, заблокировать, оспорить) принимает человек.
Раньше такие коллбеки просто сохраняли статус, и о возврате никто не узнавал.
"""

from __future__ import annotations

import html

import structlog
from aiogram import Bot


logger = structlog.get_logger(__name__)


async def alert_paid_payment_reversed(
    bot: Bot | None,
    *,
    provider: str,
    local_payment_id: int,
    user_id: int | None,
    amount_kopeks: int | None,
    status: str,
) -> None:
    logger.error(
        'Оплаченный платёж получил статус возврата/отмены — зачисление не откатано',
        provider=provider,
        local_payment_id=local_payment_id,
        user_id=user_id,
        amount_kopeks=amount_kopeks,
        status=status,
    )
    if bot is None:
        return
    amount = f'{amount_kopeks / 100:.2f} ₽' if amount_kopeks is not None else '—'
    text = (
        '⚠️ <b>Возврат / чарджбэк по оплаченному платежу</b>\n\n'
        f'Провайдер: {html.escape(provider)}\n'
        f'Платёж: #{local_payment_id}\n'
        f'Пользователь: {user_id if user_id is not None else "—"}\n'
        f'Сумма: {amount}\n'
        f'Новый статус: <code>{html.escape(status)}</code>\n\n'
        'Баланс автоматически не списан — проверьте пользователя вручную.'
    )
    try:
        from app.services.admin_notification_service import AdminNotificationService

        await AdminNotificationService(bot).send_webhook_notification(text)
    except Exception:
        logger.exception('Не удалось отправить оповещение о возврате', local_payment_id=local_payment_id)
