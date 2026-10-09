"""Диплинк ``/start promo_<КОД>``: промокод применяется сам, вводить ничего не нужно.

Ссылка (и QR) стоит на подарочных билетах. Новому человеку код запоминается и применяется сразу после
регистрации, как будто он прислал его сообщением. Зарегистрированному применяется на месте.
Перебор через ссылку ограничен тем же лимитером, что и ручной ввод.
"""

from __future__ import annotations

import structlog
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.localization.texts import get_texts


logger = structlog.get_logger(__name__)

PROMO_DEEPLINK_PREFIX = 'promo_'


def is_promo_deeplink(start_parameter: str | None) -> bool:
    return (
        bool(start_parameter)
        and start_parameter.lower().startswith(PROMO_DEEPLINK_PREFIX)
        and len(start_parameter) > len(PROMO_DEEPLINK_PREFIX)
    )


def promo_code_from(start_parameter: str) -> str:
    return start_parameter[len(PROMO_DEEPLINK_PREFIX) :]


async def claim_promo_link(
    message: types.Message, state: FSMContext, user: User | None, db: AsyncSession, start_parameter: str
) -> bool:
    """Обработать ссылку. ``True`` — параметр был промокодом и дальше его не разбирать.

    ``False`` — это не наш случай (неверный формат, нет такого кода, перебор): ``/start`` идёт обычным путём,
    а параметр может оказаться рекламной кампанией.
    """
    from app.database.crud.campaign import get_campaign_by_start_parameter
    from app.database.crud.promocode import check_promocode_validity
    from app.handlers.promocode import activate_promocode_for_registration
    from app.utils.promo_rate_limiter import promo_limiter, validate_promo_format

    code = promo_code_from(start_parameter)
    telegram_id = message.from_user.id
    if not validate_promo_format(code) or promo_limiter.is_blocked(telegram_id):
        return False

    if not (await check_promocode_validity(db, code))['valid']:
        if await get_campaign_by_start_parameter(db, start_parameter) is None:
            promo_limiter.record_failed_attempt(telegram_id)
            promo_limiter.cleanup()
        return False

    if user is None:
        await state.update_data(promocode=code)  # применится после регистрации
        logger.info('Промокод из ссылки сохранён до регистрации', telegram_id=telegram_id)
        return True

    texts = get_texts(user.language)
    result = await activate_promocode_for_registration(db, user.id, code, message.bot)
    if result['success']:
        promo_limiter.record_activation(telegram_id)
        await message.answer(texts.PROMOCODE_SUCCESS.format(description=result['description']))
    else:
        error = result.get('error')
        failures = {
            'expired': texts.PROMOCODE_EXPIRED,
            'used': texts.PROMOCODE_USED,
            'already_used_by_user': texts.PROMOCODE_USED,
        }
        await message.answer(failures.get(error, texts.PROMOCODE_INVALID))
        logger.info('Промокод из ссылки не применён', telegram_id=telegram_id, error=error)
    return True
