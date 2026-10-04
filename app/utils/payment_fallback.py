"""Когда платёж не удалось создать: предложить другие способы на ту же сумму.

Клиент не должен упираться в «Попробуйте позже»: сбой одного провайдера (как 401 у Platega)
не повод терять оплату, если рядом есть другие способы.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from app.localization.texts import get_texts


def _is_failed(callback_data: str, prefix: str, exact: bool) -> bool:
    if exact:  # только этот способ, например yookassa (карта), но не yookassa_sbp
        return callback_data.split('|')[1:2] == [prefix]
    return callback_data.startswith(f'topup_amount|{prefix}')


def fallback_methods_keyboard(
    amount_kopeks: int, language: str, failed_method_prefix: str, exact: bool = False
) -> InlineKeyboardMarkup | None:
    """Кнопки способов на ту же сумму без упавшего провайдера; ``None``, если других способов нет.

    ``failed_method_prefix`` отсекает и варианты провайдера (platega_m2, freekassa_sbp);
    ``exact=True`` убирает только сам способ.
    """
    from app.keyboards.inline import get_payment_methods_keyboard

    rows = [
        row
        for row in get_payment_methods_keyboard(amount_kopeks, language).inline_keyboard
        if row
        and all((button.callback_data or '').startswith('topup_amount|') for button in row)
        and not any(_is_failed(button.callback_data or '', failed_method_prefix, exact) for button in row)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def fallback_text(language: str, amount_kopeks: int) -> str:
    texts = get_texts(language)
    return texts.t(
        'PAYMENT_FAILED_ALTERNATIVES',
        '❌ <b>Не получилось создать платёж этим способом.</b>\n\n'
        'Сумма та же — <b>{amount} ₽</b>. Выберите другой способ:',
    ).format(amount=amount_kopeks // 100)


async def answer_creation_failed(
    message, language: str, amount_kopeks: int, failed_method_prefix: str, default_text: str, exact: bool = False
) -> None:
    """Ответ на сбой создания платежа: другие способы на ту же сумму или прежний текст ошибки."""
    keyboard = fallback_methods_keyboard(amount_kopeks, language, failed_method_prefix, exact)
    if keyboard is not None:
        await message.answer(fallback_text(language, amount_kopeks), reply_markup=keyboard)
    else:
        await message.answer(default_text)
