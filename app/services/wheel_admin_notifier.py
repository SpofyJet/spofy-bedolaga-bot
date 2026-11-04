"""Уведомление в админ-чат: кто прокрутил колесо призов, чем оплатил и что выпало.

Шлётся после коммита спина (кабинет и оплата Stars в боте) фоновой задачей: не задерживает
ответ пользователю и никогда не ломает сам спин. Бот берётся тот же, что у уведомлений о
бесплатных спинах за пополнения (регистрируется при старте unified_app).
"""

from __future__ import annotations

import asyncio
import html
from datetime import UTC, datetime

import structlog

from app.database.models import WheelSpinPaymentType


logger = structlog.get_logger(__name__)

_tasks: set[asyncio.Task] = set()


def _payment_line(payment_type: str, payment_amount: int, free_left: int | None) -> str:
    if payment_type == WheelSpinPaymentType.TOPUP_CREDIT.value:
        left = f' (осталось: {free_left})' if free_left is not None else ''
        return f'🎁 бесплатный спин{left}'
    if payment_type == WheelSpinPaymentType.TELEGRAM_STARS.value:
        return f'⭐ {payment_amount} Stars'
    if payment_type == WheelSpinPaymentType.SUBSCRIPTION_DAYS.value:
        return f'📅 {payment_amount} дн. подписки'
    return html.escape(payment_type)


def build_spin_admin_message(
    *,
    user_display: str,
    user_id_label: str,
    user_id_display: str,
    username_link: str,
    payment_type: str,
    payment_amount: int,
    free_left: int | None,
    prize_emoji: str | None,
    prize_name: str,
    promocode: str | None,
    when: str,
) -> str:
    lines = [
        '🎡 <b>СПИН КОЛЕСА ПРИЗОВ</b>',
        '',
        f'👤 <b>Пользователь:</b> {user_display}',
        f'🆔 <b>{user_id_label}:</b> {user_id_display}',
        f'📱 <b>Username:</b> {username_link}',
        '',
        f'💳 <b>Оплата:</b> {_payment_line(payment_type, payment_amount, free_left)}',
        f'🏆 <b>Выпало:</b> {html.escape(prize_emoji or "🎁")} <b>{html.escape(prize_name)}</b>',
    ]
    if promocode:
        lines.append(f'🎟️ <b>Промокод:</b> <code>{html.escape(promocode)}</code>')
    lines.extend(['', f'⏰ <i>{when}</i>'])
    return '\n'.join(lines)


async def _notify(
    user_id: int,
    payment_type: str,
    payment_amount: int,
    prize_emoji: str | None,
    prize_name: str,
    promocode: str | None,
) -> None:
    from app.database.crud.wheel import get_wheel_config
    from app.database.database import AsyncSessionLocal
    from app.database.models import User
    from app.services import wheel_topup_notifier
    from app.services.admin_notification_service import AdminNotificationService, NotificationCategory
    from app.services.wheel_service import wheel_service
    from app.utils.formatters import format_username_link
    from app.utils.timezone import format_local_datetime

    bot = wheel_topup_notifier._bot
    if bot is None:
        return
    service = AdminNotificationService(bot)
    if not service.is_enabled:
        return

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            return
        free_left = None
        if payment_type == WheelSpinPaymentType.TOPUP_CREDIT.value:
            config = await get_wheel_config(db)
            if config is not None:
                free_left = (await wheel_service.get_free_spin_state(db, user_id, config)).available
        text = build_spin_admin_message(
            user_display=service._get_user_display(user),
            user_id_label=service._get_user_identifier_label(user),
            user_id_display=service._get_user_identifier_display(user),
            username_link=format_username_link(getattr(user, 'username', None), 'отсутствует'),
            payment_type=payment_type,
            payment_amount=payment_amount,
            free_left=free_left,
            prize_emoji=prize_emoji,
            prize_name=prize_name,
            promocode=promocode,
            when=format_local_datetime(datetime.now(UTC), '%d.%m.%Y %H:%M:%S'),
        )

    await service.send_admin_notification(text, category=NotificationCategory.WHEEL)


async def _safe_notify(*args) -> None:
    try:
        await _notify(*args)
    except Exception as error:
        logger.warning('Не удалось отправить админу уведомление о спине колеса', error=str(error))


def notify_admin_about_spin(
    *,
    user_id: int,
    payment_type: str,
    payment_amount: int,
    prize_emoji: str | None,
    prize_name: str,
    promocode: str | None = None,
) -> None:
    """Поставить уведомление в фон. Вызывать после коммита спина."""
    try:
        task = asyncio.create_task(
            _safe_notify(user_id, payment_type, payment_amount, prize_emoji, prize_name, promocode)
        )
    except RuntimeError:
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
