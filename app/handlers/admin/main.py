import structlog
from aiogram import Dispatcher, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.keyboards.admin import (
    get_admin_communications_submenu_keyboard,
    get_admin_main_keyboard,
    get_admin_promo_submenu_keyboard,
    get_admin_support_submenu_keyboard,
    get_admin_system_submenu_keyboard,
    get_admin_users_submenu_keyboard,
)
from app.localization.texts import get_texts
from app.services.support_settings_service import SupportSettingsService
from app.utils.decorators import admin_required, error_handler


logger = structlog.get_logger(__name__)


def _md_bold_to_html(text: str) -> str:
    """Локали админ-подменю используют ``**bold**`` (Markdown), но заголовки также
    содержат tg-emoji-теги — это HTML. Конвертируем bold и отправляем как HTML,
    иначе Markdown-парсер показывает тег сырым текстом."""
    import re

    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)


@admin_required
@error_handler
async def show_admin_panel(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    admin_text = texts.ADMIN_PANEL
    try:
        from app.services.remnawave_service import RemnaWaveService

        remnawave_service = RemnaWaveService()
        stats = await remnawave_service.get_system_statistics()
        system_stats = stats.get('system', {})
        users_online = system_stats.get('users_online', 0)
        users_today = system_stats.get('users_last_day', 0)
        users_week = system_stats.get('users_last_week', 0)
        admin_text = admin_text.replace(
            '\n\nВыберите раздел для управления:',
            (
                f'\n\n- 🟢 Онлайн сейчас: {users_online}'
                f'\n- 📅 Онлайн сегодня: {users_today}'
                f'\n- 🗓️ На этой неделе: {users_week}'
                '\n\nВыберите раздел для управления:'
            ),
        )
    except Exception as e:
        logger.error('Не удалось получить статистику Remnawave для админ-панели', error=e)

    await callback.message.edit_text(
        admin_text, reply_markup=get_admin_main_keyboard(db_user.language), parse_mode='HTML'
    )
    await callback.answer()


@admin_required
@error_handler
async def show_users_submenu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    await callback.message.edit_text(
        _md_bold_to_html(
            texts.t('ADMIN_USERS_SUBMENU_TITLE', '👥 **Управление пользователями и подписками**\n\n')
            + texts.t('ADMIN_SUBMENU_SELECT_SECTION', 'Выберите нужный раздел:')
        ),
        reply_markup=get_admin_users_submenu_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_promo_submenu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    await callback.message.edit_text(
        _md_bold_to_html(
            texts.t('ADMIN_PROMO_SUBMENU_TITLE', '💰 **Промокоды и статистика**\n\n')
            + texts.t('ADMIN_SUBMENU_SELECT_SECTION', 'Выберите нужный раздел:')
        ),
        reply_markup=get_admin_promo_submenu_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_communications_submenu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    await callback.message.edit_text(
        _md_bold_to_html(
            texts.t('ADMIN_COMMUNICATIONS_SUBMENU_TITLE', '📨 **Коммуникации**\n\n')
            + texts.t('ADMIN_COMMUNICATIONS_SUBMENU_DESCRIPTION', 'Управление рассылками и текстами интерфейса:')
        ),
        reply_markup=get_admin_communications_submenu_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_support_submenu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    # Moderators have access only to tickets and not to settings
    is_moderator_only = not settings.is_admin(callback.from_user.id) and SupportSettingsService.is_moderator(
        callback.from_user.id
    )

    kb = get_admin_support_submenu_keyboard(db_user.language)
    if is_moderator_only:
        # Rebuild keyboard to include only tickets and back to main menu
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.t('ADMIN_SUPPORT_TICKETS', '🎫 Тикеты поддержки'), callback_data='admin_tickets'
                    )
                ],
                [InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')],
            ]
        )
    await callback.message.edit_text(
        _md_bold_to_html(
            texts.t('ADMIN_SUPPORT_SUBMENU_TITLE', '🛟 **Поддержка**\n\n')
            + (
                texts.t('ADMIN_SUPPORT_SUBMENU_DESCRIPTION_MODERATOR', 'Доступ к тикетам.')
                if is_moderator_only
                else texts.t('ADMIN_SUPPORT_SUBMENU_DESCRIPTION', 'Управление тикетами и настройками поддержки:')
            )
        ),
        reply_markup=kb,
        parse_mode='HTML',
    )
    await callback.answer()


# Moderator panel entry (from main menu quick button)
@admin_required
@error_handler
async def show_moderator_panel(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.t('ADMIN_SUPPORT_TICKETS', '🎫 Тикеты поддержки'), callback_data='admin_tickets'
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'), callback_data='back_to_menu'
                )
            ],
        ]
    )
    await callback.message.edit_text(
        texts.t('ADMIN_SUPPORT_MODERATION_TITLE', '🧑‍⚖️ <b>Модерация поддержки</b>')
        + '\n\n'
        + texts.t('ADMIN_SUPPORT_MODERATION_DESCRIPTION', 'Доступ к тикетам поддержки.'),
        parse_mode='HTML',
        reply_markup=kb,
    )
    await callback.answer()


@admin_required
@error_handler
async def show_system_submenu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    await callback.message.edit_text(
        _md_bold_to_html(
            texts.t('ADMIN_SYSTEM_SUBMENU_TITLE', '🛠️ **Системные функции**\n\n')
            + texts.t(
                'ADMIN_SYSTEM_SUBMENU_DESCRIPTION', 'Отчеты, обновления, логи, резервные копии и системные операции:'
            )
        ),
        reply_markup=get_admin_system_submenu_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_admin_panel, F.data == 'admin_panel')

    dp.callback_query.register(show_users_submenu, F.data == 'admin_submenu_users')

    dp.callback_query.register(show_promo_submenu, F.data == 'admin_submenu_promo')

    dp.callback_query.register(show_communications_submenu, F.data == 'admin_submenu_communications')

    dp.callback_query.register(show_support_submenu, F.data == 'admin_submenu_support')

    dp.callback_query.register(show_system_submenu, F.data == 'admin_submenu_system')
    dp.callback_query.register(show_moderator_panel, F.data == 'moderator_panel')
