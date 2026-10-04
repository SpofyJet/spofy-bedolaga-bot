"""Когда платёж не удалось создать: предложить другие способы на ту же сумму.

Клиент не должен упираться в «Попробуйте позже»: сбой одного провайдера (как 401 у Platega)
не повод терять оплату, если рядом есть другие способы.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from app.localization.texts import get_texts


def fallback_methods_keyboard(
    amount_kopeks: int, language: str, failed_method_prefix: str
) -> InlineKeyboardMarkup | None:
    """Кнопки способов на ту же сумму без упавшего провайдера; ``None``, если других способов нет."""
    from app.keyboards.inline import get_payment_methods_keyboard

    failed = f'topup_amount|{failed_method_prefix}'
    rows = [
        row
        for row in get_payment_methods_keyboard(amount_kopeks, language).inline_keyboard
        if row
        and all((button.callback_data or '').startswith('topup_amount|') for button in row)
        and not any((button.callback_data or '').startswith(failed) for button in row)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def fallback_text(language: str, amount_kopeks: int) -> str:
    texts = get_texts(language)
    return texts.t(
        'PAYMENT_FAILED_ALTERNATIVES',
        '❌ <b>Не получилось создать платёж этим способом.</b>\n\n'
        'Сумма та же — <b>{amount} ₽</b>. Выберите другой способ:',
    ).format(amount=amount_kopeks // 100)
