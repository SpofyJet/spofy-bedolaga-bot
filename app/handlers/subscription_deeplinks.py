"""Spofy: диплинки ``/start renew`` и ``/start traffic``.

Ведут со страницы подписки (sub.spofyltd.ru), из уведомления «обходы отключены» и из-под
постов в канале прямо к продлению или докупке трафика. Экраны продления и докупки построены
на редактировании сообщения с кнопкой, поэтому из /start человек получает короткое
сообщение с одной кнопкой — один тап до нужного экрана.

``renew_<источник>`` (например ``renew_ch1212`` под постом в канале) — то же, что ``renew``;
источник пишется в событие ``renew_link_open``, по нему считаем переходы с каждого поста.
Кнопка под постом одна на всех, поэтому ``renew`` отвечает каждому по его подписке:

* платная — выбор срока продления;
* «Навсегда» — продлевать нечего, так и говорим;
* подписки нет или пробная без тарифа — выбор тарифа (раньше без подписки открывалось
  обычное меню, а пробным показывался лишний экран «Пробный период заканчивается»).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import structlog
from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.subscription import get_subscription_by_user_id
from app.database.models import SubscriptionEvent
from app.localization.texts import get_texts
from app.utils.lifetime import is_lifetime_end
from app.utils.miniapp_buttons import build_miniapp_or_callback_button, build_subscription_extend_button


logger = structlog.get_logger(__name__)

RENEW_DEEPLINK = 'renew'
TRAFFIC_DEEPLINK = 'traffic'
EVENT_RENEW_LINK_OPEN = 'renew_link_open'  # не 'funnel_*': иначе глушит напоминания воронки
_SOURCE_MAX_LENGTH = 32
_SOURCE_FORBIDDEN = re.compile(r'[^A-Za-z0-9_-]')


def subscription_deeplink_action(start_parameter: str | None) -> str | None:
    """``renew`` и ``renew_<источник>`` → ``'renew'``, ``traffic`` → ``'traffic'``, остальное → None."""
    if not start_parameter:
        return None
    if start_parameter == TRAFFIC_DEEPLINK:
        return TRAFFIC_DEEPLINK
    if start_parameter == RENEW_DEEPLINK or start_parameter.startswith(f'{RENEW_DEEPLINK}_'):
        return RENEW_DEEPLINK
    return None


def subscription_deeplink_source(start_parameter: str | None) -> str:
    """``renew_ch1212`` → ``ch1212``; без метки — пустая строка."""
    if not start_parameter or '_' not in start_parameter:
        return ''
    return _SOURCE_FORBIDDEN.sub('', start_parameter.split('_', 1)[1])[:_SOURCE_MAX_LENGTH]


def _renew_reply(texts, subscription) -> tuple[str, str, types.InlineKeyboardButton | None]:
    """Вид ответа (он же идёт в событие), текст и кнопка — по подписке человека."""
    if subscription is None or (subscription.is_trial and not subscription.tariff_id):
        return (
            'buy',
            texts.get('DEEPLINK_BUY_TEXT', '💎 <b>Выбор тарифа</b>'),
            build_miniapp_or_callback_button(
                text=texts.get('MENU_BUY_SUBSCRIPTION', '💎 Купить подписку'),
                callback_data='menu_buy',
                style='success',
            ),
        )
    if not subscription.is_trial and is_lifetime_end(subscription.end_date):
        return (
            'lifetime',
            texts.get('SUBSCRIPTION_LIFETIME_NO_RENEW', '♾️ Подписка действует навсегда — продлевать не нужно.'),
            None,
        )
    return (
        'trial' if subscription.is_trial else 'renew',
        texts.get('DEEPLINK_RENEW_TEXT', '⏰ <b>Продление подписки</b>'),
        build_subscription_extend_button(
            texts.get('BYPASS_RENEW_BUTTON', '⏰ Продлить подписку'), subscription.id, style='success'
        ),
    )


async def _record_renew_open(db: AsyncSession, user_id: int, kind: str, source: str, subscription) -> None:
    """Событие перехода по ссылке. Ответ человеку уже ушёл: сбой записи его не касается."""
    try:
        db.add(
            SubscriptionEvent(
                user_id=user_id,
                subscription_id=getattr(subscription, 'id', None),
                event_type=EVENT_RENEW_LINK_OPEN,
                message=f'{kind}:{source}',
                occurred_at=datetime.now(UTC),
            )
        )
        await db.commit()
    except Exception as error:
        logger.warning('Диплинк renew: не записали переход', user_id=user_id, error=str(error))
        try:
            await db.rollback()
        except Exception:
            logger.debug('Ignored error in _record_renew_open', exc_info=True)


async def open_subscription_deeplink(
    message: types.Message, user, db: AsyncSession, action: str, *, source: str = ''
) -> bool:
    """Ответить на диплинк. False — ответить нечем (``traffic`` без подписки): пусть отработает обычный /start."""
    subscription = await get_subscription_by_user_id(db, user.id)
    texts = get_texts(user.language)

    if action == TRAFFIC_DEEPLINK:
        if subscription is None:
            return False
        button = build_miniapp_or_callback_button(
            text=texts.get('BYPASS_BUY_TRAFFIC_BUTTON', '📈 Докупить трафик'),
            callback_data='buy_traffic',
            style='success',
        )
        await message.answer(
            texts.get('DEEPLINK_TRAFFIC_TEXT', '📈 <b>Докупка трафика</b>'),
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[button]]),
        )
        return True

    kind, text, button = _renew_reply(texts, subscription)
    await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[button]]) if button else None)
    await _record_renew_open(db, user.id, kind, source, subscription)
    logger.info('Ссылка продления открыта', user_id=user.id, kind=kind, source=source or '-')
    return True
