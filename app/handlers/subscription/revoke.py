"""Handler for subscription reissue (revoke + regenerate link)."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InaccessibleMessage, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Subscription, User
from app.localization.texts import get_texts
from app.services.subscription_service import SubscriptionService
from app.utils.decorators import error_handler


logger = structlog.get_logger(__name__)


def _check_revoke_cooldown(subscription: Subscription) -> int | None:
    """Returns remaining seconds if on cooldown, None if ready."""
    if not subscription.last_revoke_at:
        return None
    elapsed = (datetime.now(UTC) - subscription.last_revoke_at).total_seconds()
    cooldown = settings.SUBSCRIPTION_REVOKE_COOLDOWN_SECONDS
    if elapsed < cooldown:
        return int(cooldown - elapsed)
    return None


def _build_revoke_confirm_keyboard(language: str) -> InlineKeyboardMarkup:
    """Build confirmation keyboard for revoke action."""
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.t('SUBSCRIPTION_REVOKE_CONFIRM_BTN', '✅ Подтвердить'),
                    callback_data='subscription_revoke_confirm',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BACK,
                    callback_data='subscription_settings',
                ),
            ],
        ]
    )


def _build_revoke_success_keyboard(language: str) -> InlineKeyboardMarkup:
    """Build success keyboard with connect and back buttons."""
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.t('SUBSCRIPTION_REVOKE_CONNECT_BTN', '🔗 Подключиться'),
                    callback_data='subscription_connect',
                    style='success',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=texts.BACK,
                    callback_data='menu_subscription',
                ),
            ],
        ]
    )


@error_handler
async def start_subscription_revoke(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    """Show revoke confirmation for classic single-subscription mode."""
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)

    if not settings.is_subscription_revoke_enabled():
        await callback.answer(
            texts.t('SUBSCRIPTION_REVOKE_DISABLED', 'Перевыпуск подписки недоступен'),
            show_alert=True,
        )
        return

    subscription = db_user.subscription
    if not subscription or not subscription.is_active:
        await callback.answer(
            texts.t('SUBSCRIPTION_NOT_FOUND', 'Подписка не найдена'),
            show_alert=True,
        )
        return

    # Check cooldown
    remaining = _check_revoke_cooldown(subscription)
    if remaining is not None:
        minutes = remaining // 60
        seconds = remaining % 60
        await callback.answer(
            texts.t(
                'SUBSCRIPTION_REVOKE_COOLDOWN',
                '⏱ Перевыпуск будет доступен через {minutes} мин. {seconds} сек.',
            ).format(minutes=minutes, seconds=seconds),
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        texts.t(
            'SUBSCRIPTION_REVOKE_WARNING',
            (
                '⚠️ <b>Перевыпуск подписки</b>\n\n'
                'Это действие:\n'
                '• Сгенерирует новую ссылку подключения\n'
                '• Сбросит все подключённые устройства\n'
                '• Старая ссылка перестанет работать\n\n'
                'Продолжить?'
            ),
        ),
        reply_markup=_build_revoke_confirm_keyboard(db_user.language),
        parse_mode='HTML',
    )


@error_handler
async def confirm_subscription_revoke(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    """Execute revoke of the user's subscription."""
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)

    if not settings.is_subscription_revoke_enabled():
        await callback.answer(
            texts.t('SUBSCRIPTION_REVOKE_DISABLED', 'Перевыпуск подписки недоступен'),
            show_alert=True,
        )
        return

    subscription = db_user.subscription

    if not subscription or not subscription.is_active:
        await callback.answer(
            texts.t('SUBSCRIPTION_NOT_FOUND', 'Подписка не найдена'),
            show_alert=True,
        )
        return

    # TOCTOU protection: re-check cooldown
    remaining = _check_revoke_cooldown(subscription)
    if remaining is not None:
        minutes = remaining // 60
        seconds = remaining % 60
        await callback.answer(
            texts.t(
                'SUBSCRIPTION_REVOKE_COOLDOWN',
                '⏱ Перевыпуск будет доступен через {minutes} мин. {seconds} сек.',
            ).format(minutes=minutes, seconds=seconds),
            show_alert=True,
        )
        return

    # Answer callback BEFORE heavy operation
    await callback.answer()

    # Execute revoke
    sub_service = SubscriptionService()
    result = await sub_service.revoke_subscription(db, subscription)

    if not result:
        await callback.message.edit_text(
            texts.t('SUBSCRIPTION_REVOKE_ERROR', '❌ Ошибка при перевыпуске подписки. Попробуйте позже.'),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')],
                ]
            ),
            parse_mode='HTML',
        )
        return

    # Update cooldown timestamp
    subscription.last_revoke_at = datetime.now(UTC)
    await db.commit()

    logger.info(
        'Subscription revoked successfully',
        user_id=db_user.id,
        subscription_id=subscription.id,
    )

    success_text = (
        texts.t(
            'SUBSCRIPTION_REVOKE_SUCCESS',
            (
                '✅ <b>Подписка перевыпущена!</b>\n\n'
                'Новая ссылка подключения готова. '
                'Старая ссылка больше не действительна.\n\n'
                'Все устройства были отключены.'
            ),
        )
        if result.devices_reset
        else texts.t(
            'SUBSCRIPTION_REVOKE_PARTIAL_SUCCESS',
            'Новая ссылка готова, старая больше не действует. Сбросить все устройства не удалось. Проверьте их в разделе устройств.',
        )
    )
    await callback.message.edit_text(
        success_text,
        reply_markup=_build_revoke_success_keyboard(db_user.language),
        parse_mode='HTML',
    )
