"""Кнопки уведомлений: у каждого сообщения есть следующий шаг."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.utils.miniapp_buttons import build_miniapp_or_callback_button


def subscription_button(texts) -> InlineKeyboardButton:
    return build_miniapp_or_callback_button(
        text=texts.get('MY_SUBSCRIPTION_BUTTON', '📱 Моя подписка'), callback_data='menu_subscription'
    )


def buy_button(texts) -> InlineKeyboardButton:
    return build_miniapp_or_callback_button(
        text=texts.get('MENU_BUY_SUBSCRIPTION', '💎 Купить подписку'), callback_data='menu_buy', style='success'
    )


def topup_button(texts) -> InlineKeyboardButton:
    return build_miniapp_or_callback_button(
        text=texts.get('BALANCE_TOPUP', '💳 Пополнить баланс'), callback_data='menu_balance', style='success'
    )


def buy_traffic_button(texts) -> InlineKeyboardButton:
    return build_miniapp_or_callback_button(
        text=texts.get('BYPASS_BUY_TRAFFIC_BUTTON', '📈 Докупить трафик'), callback_data='buy_traffic', style='success'
    )


def referral_button(texts) -> InlineKeyboardButton:
    return build_miniapp_or_callback_button(
        text=texts.get('MENU_REFERRALS', '🤝 Пригласить друзей'), callback_data='menu_referrals', style='success'
    )


def support_button(texts) -> InlineKeyboardButton | None:
    url = settings.get_support_contact_url()
    if not url:
        return None
    return InlineKeyboardButton(text=texts.get('CONTACT_SUPPORT_BUTTON', '💬 Задать вопрос'), url=url)


def keyboard(*buttons: InlineKeyboardButton | None) -> InlineKeyboardMarkup | None:
    """Одна кнопка в ряд; пропущенные (``None``) не показываются."""
    rows = [[button] for button in buttons if button is not None]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def admin_url(path: str) -> str | None:
    base = settings.normalized_cabinet_url()
    return f'{base}/admin/{path.lstrip("/")}' if base else None


def admin_user_card_keyboard(user) -> InlineKeyboardMarkup | None:
    """Кнопка на карточку пользователя под уведомлением в админ-чате."""
    user_id = getattr(user, 'id', None)
    url = admin_url(f'users/{user_id}') if user_id is not None else None
    if not url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='👤 Карточка пользователя', url=url)]])


def admin_startup_keyboard() -> InlineKeyboardMarkup | None:
    """Разделы админки, которые открывают чаще всего."""
    pairs = (
        ('📊 Дашборд', 'dashboard'),
        ('👥 Пользователи', 'users'),
        ('💳 Платежи', 'payments'),
        ('🎫 Обращения', 'tickets'),
    )
    buttons = [InlineKeyboardButton(text=label, url=url) for label, path in pairs if (url := admin_url(path))]
    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:]])
