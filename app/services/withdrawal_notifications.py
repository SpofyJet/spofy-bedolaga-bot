"""Сообщение пользователю о решении по заявке на вывод — одно для бота и кабинета.

Раньше тексты жили прямо в хендлерах админки бота, кабинет слал свои русские
строки, а отметка «Выплата выполнена» из кабинета не уведомляла человека вовсе.
"""

from __future__ import annotations

import html

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import User, WithdrawalRequestStatus
from app.localization.texts import get_texts


logger = structlog.get_logger(__name__)

# Причина, которую бот подставляет сам при отклонении в один тап: человеку её не показываем.
DEFAULT_BOT_REJECT_COMMENT = 'Отклонено администратором'

_TEXTS = {
    WithdrawalRequestStatus.APPROVED.value: (
        'REFERRAL_WITHDRAWAL_APPROVED',
        (
            '✅ <b>Заявка на вывод #{id} одобрена!</b>\n\n'
            'Сумма: <b>{amount}</b>\n'
            'Средства списаны с баланса.\n\n'
            'Ожидайте перевод на указанные реквизиты.'
        ),
    ),
    WithdrawalRequestStatus.REJECTED.value: (
        'REFERRAL_WITHDRAWAL_REJECTED',
        (
            '❌ <b>Заявка на вывод #{id} отклонена</b>\n\nСумма: <b>{amount}</b>\n\n'
            'Если у вас есть вопросы, обратитесь в поддержку.'
        ),
    ),
    WithdrawalRequestStatus.COMPLETED.value: (
        'REFERRAL_WITHDRAWAL_COMPLETED',
        (
            '💸 <b>Выплата по заявке #{id} выполнена!</b>\n\nСумма: <b>{amount}</b>\n\n'
            'Деньги отправлены на указанные реквизиты.'
        ),
    ),
}


def _support_keyboard(texts) -> InlineKeyboardMarkup | None:
    # «Поддержка» живёт внутри «Инфо» — та же кнопка, что в get_info_menu_keyboard
    try:
        from app.services.support_settings_service import SupportSettingsService

        support_on = SupportSettingsService.is_support_menu_enabled()
    except Exception:
        support_on = True
    if not support_on:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.MENU_SUPPORT, callback_data='menu_support')]]
    )


def build_withdrawal_status_message(
    language: str | None,
    *,
    request_id: int,
    amount_kopeks: int,
    status: str,
    comment: str | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Текст и клавиатура уведомления о новом статусе заявки на языке пользователя."""
    texts = get_texts(language)
    key, fallback = _TEXTS[status]
    amount = texts.format_price(amount_kopeks)
    comment = (comment or '').strip()
    if comment == DEFAULT_BOT_REJECT_COMMENT:
        comment = ''

    if status == WithdrawalRequestStatus.REJECTED.value:
        if comment:
            text = texts.t(
                'REFERRAL_WITHDRAWAL_REJECTED_WITH_REASON',
                '❌ <b>Заявка на вывод #{id} отклонена</b>\n\nСумма: <b>{amount}</b>\nПричина: {reason}\n\n'
                'Если у вас есть вопросы, обратитесь в поддержку.',
            ).format(id=request_id, amount=amount, reason=html.escape(comment))
        else:
            text = texts.t(key, fallback).format(id=request_id, amount=amount)
        return text, _support_keyboard(texts)

    text = texts.t(key, fallback).format(id=request_id, amount=amount)
    if comment:
        text += '\n\n' + texts.t('REFERRAL_WITHDRAWAL_ADMIN_COMMENT', 'Комментарий: {comment}').format(
            comment=html.escape(comment)
        )
    return text, None


async def notify_user_about_withdrawal_status(
    bot: Bot,
    user: User | None,
    *,
    request_id: int,
    amount_kopeks: int,
    status: str,
    comment: str | None = None,
) -> bool:
    """Шлёт уведомление в Telegram; у пользователя без telegram_id — ничего не делает."""
    if not user or not user.telegram_id:
        return False
    text, keyboard = build_withdrawal_status_message(
        user.language, request_id=request_id, amount_kopeks=amount_kopeks, status=status, comment=comment
    )
    try:
        await bot.send_message(user.telegram_id, text, reply_markup=keyboard, parse_mode='HTML')
    except Exception as error:
        logger.error(
            'Ошибка отправки уведомления пользователю о заявке на вывод',
            request_id=request_id,
            status=status,
            error=error,
        )
        return False
    return True
