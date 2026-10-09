"""Диплинк ``/start ultima`` (и ``ultima_<источник>``): личное предложение ULTIMA из канала.

Пост в канале ведёт сюда: человек нажимает кнопку и получает то же предложение, что и в рассылке,
но с **собственным часом**: скидка включается в момент нажатия, а не публикации. Метка источника
(``ultima_ch1``, ``ultima_ch2``) пишется в событие, чтобы сравнить посты по числу открытий и покупок.

Повторные нажатия: пока скидка действует, показываем остаток времени, не продлевая её; после окончания
новая выдаётся не раньше чем через ``PROMO_LINK_COOLDOWN_HOURS`` часов (по умолчанию 12; 0 отключает).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from aiogram import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import PromoOfferTemplate, SubscriptionEvent
from app.localization.texts import get_texts
from app.utils.promo_offer import TARIFF_SOURCE_PREFIX, get_user_active_promo_discount_percent


logger = structlog.get_logger(__name__)

ULTIMA_DEEPLINK = 'ultima'
EVENT_LINK_OPEN = 'ultima_link_open'


def is_ultima_deeplink(start_parameter: str | None) -> bool:
    return bool(start_parameter) and (start_parameter == ULTIMA_DEEPLINK or start_parameter.startswith('ultima_'))


def link_source(start_parameter: str | None) -> str:
    """``ultima_ch1`` → ``ch1``; просто ``ultima`` → пустая строка."""
    if not start_parameter or '_' not in start_parameter:
        return ''
    return start_parameter.split('_', 1)[1][:32]


async def _find_template(db: AsyncSession) -> PromoOfferTemplate | None:
    result = await db.execute(
        select(PromoOfferTemplate)
        .where(PromoOfferTemplate.offer_type == 'tariff_discount', PromoOfferTemplate.is_active.is_(True))
        .order_by(PromoOfferTemplate.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _record(db: AsyncSession, user_id: int, status: str, source: str) -> None:
    db.add(
        SubscriptionEvent(
            user_id=user_id,
            event_type=EVENT_LINK_OPEN,
            message=f'{status}:{source}',
            occurred_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def _activated_recently(db: AsyncSession, user_id: int, hours: int) -> bool:
    if hours <= 0:
        return False
    result = await db.execute(
        select(SubscriptionEvent.id)
        .where(
            SubscriptionEvent.user_id == user_id,
            SubscriptionEvent.event_type == EVENT_LINK_OPEN,
            SubscriptionEvent.message.like('activated:%'),
            SubscriptionEvent.created_at > datetime.now(UTC) - timedelta(hours=hours),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _minutes_left(user) -> int:
    expires = getattr(user, 'promo_offer_discount_expires_at', None)
    if expires is None:
        return 0
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return max(1, int((expires - datetime.now(UTC)).total_seconds() // 60))


async def open_ultima_offer(message: types.Message, user, db: AsyncSession, *, source: str = '') -> bool:
    """Выдать (или показать действующее) предложение ULTIMA. False — предложения нет, пусть идёт обычный /start."""
    from app.handlers.admin.promo_offers import _render_template_text, _send_prepaid_tariff_offer

    template = await _find_template(db)
    if template is None or not getattr(user, 'telegram_id', None):
        return False
    tariff_id = int(settings.PROMO_OFFER_TARIFF_ID)
    texts = get_texts(user.language)
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text=template.button_text, callback_data=f'tariff_select:{tariff_id}')]
        ]
    )

    # Скидка уже действует: показываем остаток, срок не продлеваем.
    source_value = getattr(user, 'promo_offer_discount_source', None) or ''
    if source_value.startswith(f'{TARIFF_SOURCE_PREFIX}{tariff_id}|') and (
        get_user_active_promo_discount_percent(user, tariff_id) > 0
    ):
        await _record(db, user.id, 'active', source)
        line = texts.t('ULTIMA_LINK_ACTIVE', '⏳ Предложение уже открыто, осталось {minutes} мин.').format(
            minutes=_minutes_left(user)
        )
        await message.answer(
            f'{line}\n\n{_render_template_text(template, user.language)}', reply_markup=keyboard, parse_mode='HTML'
        )
        return True

    cooldown = int(getattr(settings, 'PROMO_LINK_COOLDOWN_HOURS', 12))
    if await _activated_recently(db, user.id, cooldown):
        await _record(db, user.id, 'cooldown', source)
        await message.answer(
            texts.t(
                'ULTIMA_LINK_USED',
                'Это предложение вы уже открывали. Новая скидка будет доступна через {hours} ч. '
                'Тариф ULTIMA по обычной цене:',
            ).format(hours=cooldown),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='👑 ULTIMA', callback_data=f'tariff_select:{tariff_id}')]
                ]
            ),
        )
        return True

    sent = await _send_prepaid_tariff_offer(message.bot, db, template, user, user.language, ignore_preferences=True)
    await _record(db, user.id, 'activated' if sent else 'failed', source)
    logger.info('Ссылка ULTIMA открыта', user_id=user.id, source=source or '-', activated=bool(sent))
    return bool(sent)
