"""Подтверждение покупки одним нажатием прямо в сообщении о пополнении.

Человек выбрал тариф и срок, денег не хватило — бот сохранил корзину, человек пополнил баланс.
Раньше сообщение «Зачислено» вело на экран оформления («Продолжить оформление»), и только там
стояла кнопка «Подтвердить». Здесь решается, можно ли поставить «Подтвердить» сразу под
«Зачислено»: корзина та же, цена та же, что человек видел при выборе, и денег хватает.

Автопокупки тут нет: без нажатия ничего не списывается. Само списание делает прежний обработчик
подтверждения (``confirm_saved_cart_after_topup`` в handlers/subscription/tariff_purchase.py).
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass
from typing import Any

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.database.crud.user import get_user_by_id
from app.database.database import AsyncSessionLocal
from app.localization.texts import get_texts
from app.services.user_cart_service import user_cart_service
from app.utils.formatting import format_period, format_price_kopeks
from app.utils.lifetime import is_lifetime_period


logger = structlog.get_logger(__name__)

CONFIRM_CALLBACK_PREFIX = 'cart_confirm'
RESUME_CALLBACK = 'return_to_saved_cart'
ONE_TAP_CART_MODES = ('tariff_purchase', 'extend')
_SUBPAGE_SOURCE = 'spofy_subpage'  # = spofy_subpage_service.SUBPAGE_SOURCE: такую корзину оплачивает её же платёж

# Кому только что ушло сообщение с кнопкой подтверждения (users.id -> время). Нужно ровно
# для одного: не слать следом второе сообщение с «Продолжить оформление» про ту же корзину.
_OFFER_MARK_TTL_SECONDS = 120.0
_recent_offers: dict[int, float] = {}


@dataclass(frozen=True, slots=True)
class TopupCheckoutOffer:
    """Что именно человек подтвердит кнопкой под «Зачислено»."""

    cart_mode: str
    tariff_name: str
    period_days: int
    price_kopeks: int
    balance_kopeks: int
    token: str

    @property
    def callback_data(self) -> str:
        return f'{CONFIRM_CALLBACK_PREFIX}:{self.token}:{self.price_kopeks}:{self.balance_kopeks}'


def parse_confirm_callback(data: str | None) -> tuple[str, int, int] | None:
    """(ключ корзины, цена, баланс) из кнопки подтверждения; None — данные не наши или битые."""
    parts = (data or '').split(':')
    if len(parts) != 4 or parts[0] != CONFIRM_CALLBACK_PREFIX or not parts[1]:
        return None
    try:
        price, balance = int(parts[2]), int(parts[3])
    except ValueError:
        return None
    if price <= 0 or balance < price:
        return None
    return parts[1], price, balance


def is_one_tap_cart(cart: dict[str, Any] | None) -> bool:
    """Корзина покупки или продления тарифа, которую оформляет сам человек кнопкой в боте."""
    return (
        bool(cart)
        and cart.get('cart_mode') in ONE_TAP_CART_MODES
        and bool(cart.get('tariff_id'))
        and cart.get('source') != _SUBPAGE_SOURCE
    )


async def resolve_topup_checkout_offer(user: Any) -> TopupCheckoutOffer | None:
    """Предложение подтвердить сохранённую корзину сразу — или None, если нужен экран оформления.

    Только чтение. Корзину проверяет и пересчитывает тот же код, что и «Продолжить оформление»;
    любое расхождение (цена изменилась с момента выбора, не хватает денег, тариф или подписка
    уже не те) означает прежний путь через экран.
    """
    user_id = getattr(user, 'id', None)
    # Включённое СБП-автопродление добавляет на экран оформления выбор способа — его не прячем.
    if not user_id or settings.is_platega_recurrent_enabled():
        return None

    cart = await user_cart_service.get_user_cart(user_id)
    if not is_one_tap_cart(cart):
        return None
    try:
        saved_price = int(cart.get('total_price') or 0)
    except (TypeError, ValueError):
        return None

    # Обработчики импортируют сервисы, не наоборот: берём общий код корзины на месте вызова.
    from app.handlers.subscription.tariff_purchase import load_saved_tariff_cart, one_tap_confirm_callback

    async with AsyncSessionLocal() as db:
        db_user = await get_user_by_id(db, user_id)
        if db_user is None:
            return None
        saved, _rejection = await load_saved_tariff_cart(db, db_user, dict(cart))
        if saved is None or one_tap_confirm_callback(saved) is None:
            return None
        balance = int(db_user.balance_kopeks or 0)
        if saved.total_price != saved_price or balance < saved.total_price:
            return None
        offer = TopupCheckoutOffer(
            cart_mode=saved.cart_mode,
            tariff_name=saved.tariff.name,
            period_days=saved.period,
            price_kopeks=saved.total_price,
            balance_kopeks=balance,
            token=saved.checkout_token,
        )
    # Telegram принимает callback_data до 64 байт.
    return offer if len(offer.callback_data.encode()) <= 64 else None


def checkout_offer_line(texts: Any, offer: TopupCheckoutOffer) -> str:
    """Одна строка под «Зачислено»: что будет оформлено кнопкой, на какой срок и за сколько."""
    period = format_period(offer.period_days)
    if is_lifetime_period(offer.period_days):
        period = period.lower()
    if offer.cart_mode == 'extend':
        template = texts.t('TOPUP_CONFIRM_RENEW_LINE', 'Продление: <b>{tariff}</b>, {period} — <b>{price}</b>')
    else:
        template = texts.t('TOPUP_CONFIRM_PURCHASE_LINE', 'Покупка: <b>{tariff}</b>, {period} — <b>{price}</b>')
    return template.format(
        tariff=html.escape(offer.tariff_name),
        period=period,
        price=format_price_kopeks(offer.price_kopeks),
    )


def checkout_offer_button(texts: Any, offer: TopupCheckoutOffer) -> InlineKeyboardButton:
    """Та же кнопка «Подтвердить», что на экране оформления, с тем же текстом."""
    if offer.cart_mode == 'extend':
        text = texts.t('TARIFF_RENEW_CONFIRM_BUTTON', '✅ Подтвердить продление')
    else:
        text = texts.t('TARIFF_PURCHASE_CONFIRM_BUTTON', '✅ Подтвердить покупку')
    return InlineKeyboardButton(text=text, callback_data=offer.callback_data, style='success')


async def apply_topup_checkout_offer(
    user: Any, text: str, keyboard: Any, *, cart_notice_follows: bool = True
) -> tuple[str, Any]:
    """Сообщение о пополнении с кнопкой подтверждения вместо «Продолжить оформление».

    Меняется только случай, когда клавиатура уже ведёт к сохранённой корзине и корзину можно
    оформить сразу. Во всех остальных (нет корзины, другая корзина, кабинетный режим меню, не
    хватает денег, ошибка расчёта) текст и клавиатура возвращаются как были.

    ``cart_notice_follows=False`` — у оплаты звёздами сообщение про корзину уходит раньше этого,
    глушить после него нечего.
    """
    try:
        user_id = getattr(user, 'id', None)
        _recent_offers.pop(user_id, None)  # метка относится только к последнему сообщению о пополнении
        rows = keyboard.inline_keyboard if isinstance(keyboard, InlineKeyboardMarkup) else None
        if not rows or len(rows[0]) != 1 or rows[0][0].callback_data != RESUME_CALLBACK:
            return text, keyboard
        offer = await resolve_topup_checkout_offer(user)
        if offer is None:
            return text, keyboard
        texts = get_texts(getattr(user, 'language', None) or 'ru')
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[[checkout_offer_button(texts, offer)], *rows[1:]])
        confirm_text = f'{text}\n\n{checkout_offer_line(texts, offer)}'
        if cart_notice_follows:
            _mark_offered(user_id)
        return confirm_text, confirm_keyboard
    except Exception as error:
        # Пополнение уже зачислено: сообщение о нём обязано уйти в любом случае, пусть и с прежней кнопкой.
        logger.warning('Кнопка подтверждения в сообщении о пополнении не собрана', error=error, exc_info=True)
        return text, keyboard


def _mark_offered(user_id: int) -> None:
    now = time.monotonic()
    for stale in [uid for uid, at in _recent_offers.items() if now - at > _OFFER_MARK_TTL_SECONDS]:
        del _recent_offers[stale]
    _recent_offers[user_id] = now


def consume_recent_offer(user_id: int | None) -> bool:
    """Было ли человеку только что отправлено сообщение с кнопкой подтверждения (одноразово)."""
    marked_at = _recent_offers.pop(user_id, None) if user_id else None
    return marked_at is not None and time.monotonic() - marked_at <= _OFFER_MARK_TTL_SECONDS
