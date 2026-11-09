"""Handler for gift subscription activation via inline callback button."""

import html as html_mod

import structlog
from aiogram import Dispatcher, F, types
from aiogram.types import InaccessibleMessage, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.database.crud.user import get_user_by_telegram_id
from app.database.database import AsyncSessionLocal
from app.localization.texts import get_texts
from app.services.gift_claim_service import (
    GiftClaimAlreadyOwnedError,
    GiftClaimNotActivatableError,
    GiftClaimNotFoundError,
    GiftClaimSelfActivationError,
    claim_bound_gift_for_user,
)
from app.services.guest_purchase_service import GiftLifetimeHolderError, GuestPurchaseError
from app.utils.gift_result import gift_valid_until_line


logger = structlog.get_logger(__name__)

_GIFT_NOT_FOUND = 'Подарок не найден или недоступен.'


def _menu_keyboard(texts, *, with_subscription: bool = False) -> InlineKeyboardMarkup:
    """«Моя подписка» (после активации) и «В главное меню» — чтобы экран не был тупиком."""
    rows: list[list[InlineKeyboardButton]] = []
    if with_subscription:
        subscription_text = (
            texts.t('MY_SUBSCRIPTIONS_BUTTON', '📱 Мои подписки')
            if settings.is_multi_tariff_enabled()
            else texts.t('MY_SUBSCRIPTION_BUTTON', '📱 Моя подписка')
        )
        rows.append([InlineKeyboardButton(text=subscription_text, callback_data='menu_subscription')])
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '🏠 В главное меню'),
                callback_data='back_to_menu',
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_gift_activate(callback: types.CallbackQuery) -> None:
    """Handle gift_activate:{purchase_id} callback from Telegram notification."""
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer('Сообщение устарело. Попробуйте /start.', show_alert=True)
        return

    if not callback.data:
        return

    parts = callback.data.split(':', 1)
    if len(parts) != 2:
        await callback.answer(_GIFT_NOT_FOUND, show_alert=True)
        return

    try:
        purchase_id = int(parts[1])
    except ValueError:
        await callback.answer(_GIFT_NOT_FOUND, show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text('⏳ Активируем подарок...', parse_mode=None)

    async with AsyncSessionLocal() as db:
        user = await get_user_by_telegram_id(db, callback.from_user.id)
        if not user:
            await callback.message.edit_text(_GIFT_NOT_FOUND, parse_mode=None)
            return

        texts = get_texts(user.language)

        try:
            purchase = await claim_bound_gift_for_user(
                db,
                claimant_user_id=user.id,
                purchase_id=purchase_id,
            )
        except (GiftClaimNotFoundError, GiftClaimAlreadyOwnedError):
            await callback.message.edit_text(
                texts.t('GIFT_ACTIVATION_NOT_FOUND', _GIFT_NOT_FOUND),
                parse_mode='HTML',
                reply_markup=_menu_keyboard(texts),
            )
            return
        except GiftClaimSelfActivationError:
            await callback.message.edit_text(
                texts.t(
                    'GIFT_ACTIVATION_SELF_CLAIM_ERROR',
                    '⚠️ Нельзя активировать свой собственный подарок.\nОтправьте код другу!',
                ),
                parse_mode='HTML',
                reply_markup=_menu_keyboard(texts),
            )
            return
        except GiftClaimNotActivatableError:
            await callback.message.edit_text(
                texts.t('GIFT_ACTIVATION_NOT_ACTIVATABLE_ERROR', '❌ Этот подарок невозможно активировать.'),
                parse_mode='HTML',
                reply_markup=_menu_keyboard(texts),
            )
            return
        except GiftLifetimeHolderError:
            await callback.message.edit_text(
                texts.t(
                    'GIFT_ACTIVATION_LIFETIME_ERROR',
                    '⚠️ У вас подписка «Навсегда» — подарок к ней не применяется. Он остался неактивированным.',
                ),
                parse_mode='HTML',
                reply_markup=_menu_keyboard(texts),
            )
            return
        except GuestPurchaseError as exc:
            logger.warning(
                'Gift activation via callback failed',
                purchase_id=purchase_id,
                telegram_id=callback.from_user.id,
                error=exc.message,
            )
            if exc.status_code >= 500:
                await callback.message.edit_text(
                    texts.t(
                        'GIFT_ACTIVATION_GENERIC_ERROR',
                        'Произошла ошибка при активации. Попробуйте позже.',
                    ),
                    parse_mode='HTML',
                    reply_markup=_menu_keyboard(texts),
                )
            else:
                await callback.message.edit_text(
                    texts.t(
                        'GIFT_ACTIVATION_FAILED_PREFIX',
                        'Не удалось активировать подарок: {error}',
                    ).format(error=html_mod.escape(exc.message)),
                    parse_mode='HTML',
                    reply_markup=_menu_keyboard(texts),
                )
            return
        except Exception:
            logger.exception(
                'Unexpected error during gift activation via callback',
                purchase_id=purchase_id,
                telegram_id=callback.from_user.id,
            )
            await callback.message.edit_text(
                texts.t(
                    'GIFT_ACTIVATION_GENERIC_ERROR',
                    'Произошла ошибка при активации. Попробуйте позже.',
                ),
                parse_mode='HTML',
                reply_markup=_menu_keyboard(texts),
            )
            return

        tariff_name = html_mod.escape(purchase.tariff.name) if purchase.tariff and purchase.tariff.name else ''
        period_days = purchase.period_days
        period_text = f'{period_days} дн.' if period_days else ''
        tariff_text = f'{tariff_name} — {period_text}' if tariff_name else period_text

        await callback.message.edit_text(
            texts.t(
                'GIFT_ACTIVATION_CALLBACK_SUCCESS_TEXT',
                '✅ <b>Подарок активирован!</b>\n{tariff_text}\n\n{valid_until}',
            ).format(
                tariff_text=tariff_text,
                valid_until=await gift_valid_until_line(db, texts, user.id),
            ),
            parse_mode='HTML',
            reply_markup=_menu_keyboard(texts, with_subscription=True),
        )


def register_handlers(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_gift_activate, F.data.startswith('gift_activate:'))
