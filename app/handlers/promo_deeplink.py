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
from app.localization.loader import DEFAULT_LANGUAGE
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

    ``False`` — только если с таким параметром есть рекламная кампания: ``/start`` идёт обычным путём.
    Во всех остальных случаях человек получает ответ про код (истёк, исчерпан, не найден, перебор),
    а не «Вы уже зарегистрированы… реферальная ссылка не может быть применена» и не тишину.
    """
    from app.database.crud.campaign import get_campaign_by_start_parameter
    from app.database.crud.promocode import check_promocode_validity
    from app.handlers.promocode import (
        activate_promocode_for_registration,
        promo_subscription_choice_keyboard,
        promocode_error_text,
        wheel_spin_keyboard,
    )
    from app.utils.promo_rate_limiter import promo_limiter, validate_promo_format

    code = promo_code_from(start_parameter)
    telegram_id = message.from_user.id
    texts = get_texts(user.language if user else DEFAULT_LANGUAGE)

    async def is_campaign() -> bool:
        return await get_campaign_by_start_parameter(db, start_parameter) is not None

    if not validate_promo_format(code):
        if await is_campaign():
            return False
        await message.answer(texts.PROMOCODE_INVALID)
        return True

    if promo_limiter.is_blocked(telegram_id):
        if await is_campaign():
            return False
        await message.answer(
            texts.t('PROMO_RATE_LIMITED', '⏳ Слишком много попыток. Попробуйте через {cooldown} сек.').format(
                cooldown=promo_limiter.get_block_cooldown(telegram_id)
            )
        )
        return True

    validity = await check_promocode_validity(db, code)
    if not validity['valid']:
        if await is_campaign():
            return False
        if validity.get('error') == 'not_found':
            promo_limiter.record_failed_attempt(telegram_id)
            promo_limiter.cleanup()
        # Истёк / исчерпан / не найден — говорим прямо, в том числе новому человеку до регистрации.
        await message.answer(promocode_error_text(texts, validity.get('error')))
        logger.info('Промокод из ссылки недействителен', telegram_id=telegram_id, error=validity.get('error'))
        return True

    if user is None:
        await state.update_data(promocode=code)  # применится после регистрации
        logger.info('Промокод из ссылки сохранён до регистрации', telegram_id=telegram_id)
        return True

    result = await activate_promocode_for_registration(db, user.id, code, message.bot)
    if result['success']:
        promo_limiter.record_activation(telegram_id)
        await message.answer(
            texts.PROMOCODE_SUCCESS.format(description=result['description']),
            reply_markup=wheel_spin_keyboard(result, texts),
        )
    elif result.get('error') == 'select_subscription':
        # Несколько подписок — тот же выбор, что при ручном вводе (promo_sub:<id>:<код>).
        await message.answer(
            texts.t('PROMOCODE_SELECT_SUBSCRIPTION', '🎟️ К какой подписке применить промокод?'),
            reply_markup=promo_subscription_choice_keyboard(result, code),
        )
    else:
        error = result.get('error')
        await message.answer(promocode_error_text(texts, error))
        logger.info('Промокод из ссылки не применён', telegram_id=telegram_id, error=error)
    return True
