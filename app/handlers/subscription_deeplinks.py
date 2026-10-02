"""Spofy: диплинки ``/start renew`` и ``/start traffic``.

Ведут со страницы подписки (sub.spofyltd.ru) и из уведомления «обходы отключены»
прямо к продлению или докупке трафика. Экраны продления и докупки построены на
редактировании сообщения с кнопкой, поэтому из /start человек получает короткое
сообщение с одной кнопкой — один тап до нужного экрана.
"""

from __future__ import annotations

from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.subscription import get_subscription_by_user_id
from app.localization.texts import get_texts
from app.utils.miniapp_buttons import build_miniapp_or_callback_button, build_subscription_extend_button


SUBSCRIPTION_DEEPLINKS = frozenset({'renew', 'traffic'})


async def open_subscription_deeplink(message: types.Message, user, db: AsyncSession, action: str) -> bool:
    """Ответить на диплинк. False — подписки нет: пусть отработает обычный /start."""
    subscription = await get_subscription_by_user_id(db, user.id)
    if subscription is None:
        return False

    texts = get_texts(user.language)
    if action == 'traffic':
        text = texts.get('DEEPLINK_TRAFFIC_TEXT', '📈 <b>Докупка трафика</b>')
        button = build_miniapp_or_callback_button(
            text=texts.get('BYPASS_BUY_TRAFFIC_BUTTON', '📈 Докупить трафик'), callback_data='buy_traffic'
        )
    else:
        text = texts.get('DEEPLINK_RENEW_TEXT', '⏰ <b>Продление подписки</b>')
        button = build_subscription_extend_button(
            texts.get('BYPASS_RENEW_BUTTON', '⏰ Продлить подписку'), subscription.id
        )
    await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[button]]))
    return True
