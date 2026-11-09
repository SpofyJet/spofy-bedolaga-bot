from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.handlers.subscription.autopay import handle_subscription_cancel
from app.handlers.subscription.purchase import (
    clear_saved_cart,
    save_cart_and_redirect_to_topup,
)


@pytest.fixture
def mock_callback_query():
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = 'subscription_confirm'
    return callback


@pytest.fixture
def mock_user():
    user = AsyncMock(spec=User)
    user.id = 12345
    user.telegram_id = 12345
    user.language = 'ru'
    user.balance_kopeks = 10000
    user.subscription = None
    user.has_had_paid_subscription = False
    user.promo_group = None
    user.promo_group_id = None
    user.get_primary_promo_group = MagicMock(return_value=None)
    user.get_promo_discount = MagicMock(return_value=0)
    user.promo_offer_discount_percent = 0
    user.promo_offer_discount_expires_at = None
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    return db


@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(
        return_value={'period_days': 30, 'countries': ['ru'], 'devices': 2, 'traffic_gb': 10, 'total_price': 50000}
    )
    state.set_data = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


async def test_save_cart_and_redirect_to_topup(mock_callback_query, mock_state, mock_user, mock_db):
    """Тест сохранения корзины и перенаправления к пополнению"""
    # Мокаем все зависимости
    with (
        patch('app.handlers.subscription.purchase.user_cart_service') as mock_cart_service,
        patch('app.handlers.subscription.purchase.get_payment_methods_keyboard_with_cart') as mock_keyboard_func,
        patch('app.localization.texts.get_texts') as mock_get_texts,
    ):
        # Подготовим моки
        mock_cart_service.save_user_cart = AsyncMock(return_value=True)
        mock_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text='✅', callback_data='confirm')]]
        )
        mock_keyboard_func.return_value = mock_keyboard

        # Подготовим тексты
        mock_texts = AsyncMock()
        mock_texts.format_price = lambda x: f'{x / 100:.0f} ₽'
        mock_get_texts.return_value = mock_texts

        missing_amount = 40000  # 50000 - 10000 = 40000

        # Вызываем функцию
        await save_cart_and_redirect_to_topup(mock_callback_query, mock_state, mock_user, missing_amount)

        # Проверяем, что данные были сохранены в корзину
        mock_cart_service.save_user_cart.assert_called_once()
        args, kwargs = mock_cart_service.save_user_cart.call_args
        saved_user_id, saved_cart_data = args

        assert saved_user_id == mock_user.id
        assert saved_cart_data['period_days'] == 30
        assert saved_cart_data['countries'] == ['ru']
        assert saved_cart_data['devices'] == 2
        assert saved_cart_data['traffic_gb'] == 10
        assert saved_cart_data['total_price'] == 50000
        assert saved_cart_data['saved_cart'] is True
        assert saved_cart_data['missing_amount'] == missing_amount
        assert saved_cart_data['return_to_cart'] is True
        assert saved_cart_data['user_id'] == mock_user.id

        # Проверяем, что сообщение было отредактировано
        mock_callback_query.message.edit_text.assert_called_once()

        # В этой функции нет вызова callback.answer()
        # mock_callback_query.answer не должен быть вызван
        mock_callback_query.answer.assert_not_called()


async def test_clear_saved_cart(mock_callback_query, mock_state, mock_user, mock_db):
    """Тест очистки сохраненной корзины"""
    # Мокаем все зависимости
    with (
        patch('app.handlers.subscription.purchase.user_cart_service') as mock_cart_service,
        patch('app.handlers.menu.show_main_menu') as mock_show_main_menu,
    ):
        mock_cart_service.delete_user_cart = AsyncMock(return_value=True)
        mock_show_main_menu.return_value = AsyncMock()

        # Вызываем функцию
        await clear_saved_cart(mock_callback_query, mock_state, mock_user, mock_db)

        # Проверяем, что корзина удалена из сервиса
        mock_cart_service.delete_user_cart.assert_called_once_with(mock_user.id)

        # Проверяем, что FSM очищен
        mock_state.clear.assert_called_once()

        # Проверяем, что вызван answer
        mock_callback_query.answer.assert_called_once()


async def test_handle_subscription_cancel_clears_saved_cart(mock_callback_query, mock_state, mock_user, mock_db):
    """Отмена покупки должна очищать сохраненную корзину"""
    mock_show_main_menu = AsyncMock()

    with (
        patch('app.handlers.subscription.autopay.user_cart_service') as mock_cart_service,
        patch('app.localization.texts.get_texts', return_value=MagicMock()) as _,
        patch('app.handlers.menu.show_main_menu', new=mock_show_main_menu),
    ):
        mock_cart_service.get_user_cart = AsyncMock(return_value=None)
        mock_cart_service.delete_user_cart = AsyncMock(return_value=True)

        await handle_subscription_cancel(mock_callback_query, mock_state, mock_user, mock_db)

        mock_state.clear.assert_called_once()
        mock_cart_service.delete_user_cart.assert_awaited_once_with(mock_user.id)
        mock_show_main_menu.assert_awaited_once_with(mock_callback_query, mock_user, mock_db)
        mock_callback_query.answer.assert_called_once_with('❌ Покупка отменена')


async def test_handle_subscription_cancel_clears_only_current_subscription_cart(
    mock_callback_query, mock_state, mock_user, mock_db
):
    """Отмена покупки в мультитарифном сценарии чистит только корзину текущей подписки"""
    mock_show_main_menu = AsyncMock()

    with (
        patch('app.handlers.subscription.autopay.user_cart_service') as mock_cart_service,
        patch('app.localization.texts.get_texts', return_value=MagicMock()) as _,
        patch('app.handlers.menu.show_main_menu', new=mock_show_main_menu),
    ):
        # First read returns the per-subscription cart; second (global) read still
        # references the same subscription, so the global key is cleaned up too.
        mock_cart_service.get_user_cart = AsyncMock(side_effect=[{'subscription_id': 777}, {'subscription_id': 777}])
        mock_cart_service.delete_subscription_cart = AsyncMock(return_value=True)
        mock_cart_service.delete_global_cart_only = AsyncMock(return_value=True)
        mock_cart_service.delete_user_cart = AsyncMock(return_value=True)

        await handle_subscription_cancel(mock_callback_query, mock_state, mock_user, mock_db)

        mock_state.clear.assert_called_once()
        # Money-safe: only the current subscription's cart is removed; the broad
        # delete_user_cart that could nuke other subscriptions' carts is NOT called.
        mock_cart_service.delete_subscription_cart.assert_awaited_once_with(mock_user.id, 777)
        mock_cart_service.delete_global_cart_only.assert_awaited_once_with(mock_user.id)
        mock_cart_service.delete_user_cart.assert_not_called()
        mock_show_main_menu.assert_awaited_once_with(mock_callback_query, mock_user, mock_db)
        mock_callback_query.answer.assert_called_once_with('❌ Покупка отменена')
