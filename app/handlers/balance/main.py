import html
from decimal import Decimal, InvalidOperation

import structlog
from aiogram import Dispatcher, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InaccessibleMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.transaction import get_user_history_page
from app.database.models import TransactionType, User
from app.keyboards.inline import (
    get_back_keyboard,
    get_balance_keyboard,
    get_pagination_keyboard,
    get_payment_error_keyboard,
    get_payment_methods_keyboard,
)
from app.localization.texts import get_texts
from app.states import BalanceStates
from app.utils.decorators import error_handler
from app.utils.timezone import format_local_datetime
from app.utils.topup_retry import MAX_MANUAL_TOPUP_RUBLES, MIN_MANUAL_TOPUP_RUBLES, format_topup_amount_retry


logger = structlog.get_logger(__name__)

TRANSACTIONS_PER_PAGE = 10

CREDIT_TRANSACTION_TYPES: frozenset[str] = frozenset(
    {
        TransactionType.DEPOSIT.value,
        TransactionType.REFERRAL_REWARD.value,
        TransactionType.REFUND.value,
        TransactionType.POLL_REWARD.value,
    }
)


async def route_payment_by_method(
    message: types.Message, db_user: User, amount_kopeks: int, state: FSMContext, payment_method: str
) -> bool:
    """
    Роутер платежей по методу оплаты.

    Args:
        message: Сообщение для ответа
        db_user: Пользователь БД
        amount_kopeks: Сумма в копейках
        state: FSM состояние
        payment_method: Метод оплаты (stars, cryptobot и т.д.)

    Returns:
        True если платеж обработан, False если метод неизвестен
    """
    if payment_method == 'stars':
        from .stars import process_stars_payment_amount

        await process_stars_payment_amount(message, db_user, amount_kopeks, state)
        return True

    # Все остальные методы требуют сессию БД
    from app.database.database import AsyncSessionLocal

    if payment_method == 'platega':
        from .platega import process_platega_payment_amount

        async with AsyncSessionLocal() as db:
            await process_platega_payment_amount(message, db_user, db, amount_kopeks, state)
        return True

    if payment_method == 'wata':
        from .wata import process_wata_payment_amount

        async with AsyncSessionLocal() as db:
            await process_wata_payment_amount(message, db_user, db, amount_kopeks, state)
        return True

    if payment_method == 'cryptobot':
        from .cryptobot import process_cryptobot_payment_amount

        async with AsyncSessionLocal() as db:
            await process_cryptobot_payment_amount(message, db_user, db, amount_kopeks, state)
        return True

    if payment_method == 'xrocket':
        from .xrocket import process_xrocket_payment_amount

        async with AsyncSessionLocal() as db:
            await process_xrocket_payment_amount(message, db_user, db, amount_kopeks, state)
        return True

    if payment_method == 'pay2328':
        from .pay2328 import process_pay2328_payment_amount

        async with AsyncSessionLocal() as db:
            await process_pay2328_payment_amount(message, db_user, db, amount_kopeks, state)
        return True

    return False


@error_handler
async def show_balance_menu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # Проверяем, доступно ли сообщение
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)

    balance_text = texts.BALANCE_INFO.format(balance=texts.format_price(db_user.balance_kopeks))

    from app.keyboards.inline import _wheel_spins_for_menu

    reply_markup = get_balance_keyboard(db_user.language, await _wheel_spins_for_menu(db, db_user))

    try:
        if callback.message and callback.message.text:
            await callback.message.edit_text(balance_text, reply_markup=reply_markup)
        elif callback.message and callback.message.caption:
            await callback.message.edit_caption(balance_text, reply_markup=reply_markup)
        else:
            await callback.message.answer(balance_text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        logger.warning('Failed to edit balance message, sending a new one instead', error=error)
        await callback.message.answer(balance_text, reply_markup=reply_markup)
    await callback.answer()


@error_handler
async def show_balance_history(callback: types.CallbackQuery, db_user: User, db: AsyncSession, page: int = 1):
    texts = get_texts(db_user.language)

    page = max(page, 1)
    unique_transactions, total_unique = await get_user_history_page(
        db, db_user.id, page=page, per_page=TRANSACTIONS_PER_PAGE
    )
    total_pages = (total_unique + TRANSACTIONS_PER_PAGE - 1) // TRANSACTIONS_PER_PAGE

    if not unique_transactions and total_pages and page > total_pages:
        # Старая кнопка страницы, которой уже нет (операций стало меньше) — показываем последнюю.
        page = total_pages
        unique_transactions, total_unique = await get_user_history_page(
            db, db_user.id, page=page, per_page=TRANSACTIONS_PER_PAGE
        )

    if not unique_transactions:
        await callback.message.edit_text(
            texts.t('BALANCE_HISTORY_EMPTY', '📊 История операций пуста'),
            reply_markup=get_back_keyboard(db_user.language, callback_data='menu_balance'),
        )
        await callback.answer()
        return

    text = texts.t('BALANCE_HISTORY_TITLE', '📊 <b>История операций</b>') + '\n\n'

    for transaction in unique_transactions:
        is_credit = transaction.type in CREDIT_TRANSACTION_TYPES
        emoji = '💰' if is_credit else '💸'
        amount_text = (
            f'+{texts.format_price(transaction.amount_kopeks)}'
            if is_credit
            else f'-{texts.format_price(abs(transaction.amount_kopeks))}'
        )

        text += f'{emoji} {amount_text}\n'
        text += f'📝 {html.escape(transaction.description or "")}\n'
        text += f'📅 {format_local_datetime(transaction.created_at, "%d.%m.%Y %H:%M")}\n\n'

    keyboard = []

    if total_pages > 1:
        pagination_row = get_pagination_keyboard(page, total_pages, 'balance_history', db_user.language)
        keyboard.extend(pagination_row)

    keyboard.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_balance')])

    await callback.message.edit_text(
        text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='HTML'
    )
    await callback.answer()


@error_handler
async def handle_balance_history_pagination(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    page = int(callback.data.split('_')[-1])
    await show_balance_history(callback, db_user, db, page)


@error_handler
async def show_payment_methods(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    from app.config import settings
    from app.utils.payment_utils import get_payment_methods_text

    texts = get_texts(db_user.language)

    # Проверка ограничения на пополнение
    if db_user.restriction_topup:
        reason = html.escape(db_user.restriction_reason or 'Действие ограничено администратором')
        support_url = settings.get_support_contact_url()
        keyboard = []
        if support_url:
            keyboard.append([types.InlineKeyboardButton(text='🆘 Обжаловать', url=support_url)])
        keyboard.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_balance')])

        await callback.message.edit_text(
            f'🚫 <b>Пополнение ограничено</b>\n\n{reason}\n\n'
            'Если вы считаете это ошибкой, вы можете обжаловать решение.',
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        )
        await callback.answer()
        return

    payment_text = get_payment_methods_text(db_user.language)

    # Проверяем сохранённую корзину для автоподстановки суммы пополнения
    amount_kopeks = 0
    try:
        from app.services.user_cart_service import user_cart_service

        cart_data = await user_cart_service.get_user_cart(db_user.id)
        if cart_data and cart_data.get('saved_cart'):
            missing = cart_data.get('missing_amount', 0)
            if missing > 0:
                amount_kopeks = missing
    except Exception:
        logger.warning('Ignored error in show_payment_methods', exc_info=True)

    full_text = payment_text
    if amount_kopeks > 0:
        # Сумма из корзины уже подставлена в кнопки способов — говорим её словами, иначе
        # человек выбирал способ, не зная, сколько заплатит.
        full_text = (
            texts.t('PAYMENT_METHODS_AMOUNT_TITLE', '💳 <b>К оплате: {amount}</b>').format(
                amount=settings.format_price(amount_kopeks)
            )
            + '\n\n'
            + texts.t('PAYMENT_METHODS_PROMPT', 'Выберите способ оплаты:')
            + '\n\n'
        )

    keyboard = get_payment_methods_keyboard(amount_kopeks, db_user.language)
    if amount_kopeks > 0:
        # n23: корзина предзаполнила сумму — все кнопки способов ведут на оплату
        # ровно её. Даём выход к произвольной сумме, иначе до истечения TTL
        # корзины (1 час) юзер не может пополнить на свою сумму.
        keyboard.inline_keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=texts.t('TOPUP_OTHER_AMOUNT', '💰 Другая сумма'),
                    callback_data='topup_other_amount',
                )
            ]
        )

    # Если сообщение недоступно, отправляем новое
    if isinstance(callback.message, InaccessibleMessage):
        await callback.message.answer(full_text, reply_markup=keyboard, parse_mode='HTML')
        await callback.answer()
        return

    try:
        await callback.message.edit_text(full_text, reply_markup=keyboard, parse_mode='HTML')
    except TelegramBadRequest:
        try:
            await callback.message.edit_caption(full_text, reply_markup=keyboard, parse_mode='HTML')
        except TelegramBadRequest:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.message.answer(full_text, reply_markup=keyboard, parse_mode='HTML')

    await callback.answer()


@error_handler
async def show_payment_methods_other_amount(callback: types.CallbackQuery, db_user: User):
    """«Другая сумма»: способы оплаты без предзаполненной суммы корзины —
    кнопки ведут на классический ввод произвольной суммы (topup_<метод>)."""
    from app.utils.payment_utils import get_payment_methods_text

    full_text = get_payment_methods_text(db_user.language)
    keyboard = get_payment_methods_keyboard(0, db_user.language)
    try:
        await callback.message.edit_text(full_text, reply_markup=keyboard, parse_mode='HTML')
    except TelegramBadRequest:
        await callback.message.answer(full_text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()


@error_handler
async def handle_payment_methods_unavailable(callback: types.CallbackQuery, db_user: User):
    texts = get_texts(db_user.language)

    await callback.answer(
        texts.t(
            'PAYMENT_METHODS_UNAVAILABLE_ALERT',
            '⚠️ В данный момент автоматические способы оплаты временно недоступны. Для пополнения баланса обратитесь в техподдержку.',
        ),
        show_alert=True,
    )


@error_handler
async def handle_successful_topup_with_cart(user_id: int, amount_kopeks: int, bot, db: AsyncSession):
    from aiogram.fsm.storage.base import StorageKey

    from app.bot import dp
    from app.database.crud.user import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if not user:
        return

    # Email-only users don't have telegram_id - skip Telegram notification
    if not user.telegram_id:
        logger.info('Skipping cart notification for email-only user', user_id=user_id)
        return

    storage = dp.storage
    key = StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)

    try:
        state_data = await storage.get_data(key)
        current_state = await storage.get_state(key)

        if current_state == 'SubscriptionStates:cart_saved_for_topup' and state_data.get('saved_cart'):
            texts = get_texts(user.language)
            total_price = state_data.get('total_price', 0)

            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='🛒 Вернуться к оформлению подписки', callback_data='return_to_saved_cart'
                        )
                    ],
                    [types.InlineKeyboardButton(text='💰 Мой баланс', callback_data='menu_balance')],
                    [types.InlineKeyboardButton(text='🏠 В главное меню', callback_data='back_to_menu')],
                ]
            )

            if 0 < total_price <= user.balance_kopeks:
                balance_hint = 'Средств на балансе достаточно для оформления.'
            else:
                missing = max(total_price - user.balance_kopeks, 0)
                # Без округления, иначе при не хватке <50 копеек покажется «0 ₽».
                balance_hint = f'Не хватает: {texts.format_price(missing, round_kopeks=False)}'

            success_text = (
                f'✅ Баланс пополнен на {texts.format_price(amount_kopeks)}!\n\n'
                f'💰 Текущий баланс: {texts.format_price(user.balance_kopeks)}\n\n'
                f'🛒 У вас есть сохранённая корзина на {texts.format_price(total_price)}\n'
                f'{balance_hint}\n\n'
                f'Хотите продолжить оформление?'
            )

            await bot.send_message(
                chat_id=user.telegram_id, text=success_text, reply_markup=keyboard, parse_mode='HTML'
            )

    except Exception as e:
        logger.error('Ошибка обработки успешного пополнения с корзиной', error=e)


@error_handler
async def request_support_topup(callback: types.CallbackQuery, db_user: User):
    texts = get_texts(db_user.language)

    if not settings.is_support_topup_enabled():
        await callback.answer(
            texts.t(
                'SUPPORT_TOPUP_DISABLED',
                'Пополнение через поддержку отключено. Попробуйте другой способ оплаты.',
            ),
            show_alert=True,
        )
        return

    user_id_display = db_user.telegram_id or db_user.email or f'#{db_user.id}'
    # Без «⏰ 1–24 часа» и списка «криптовалюта / переводы»: обещание срока и способов, которые
    # никто не гарантирует. Только то, что нужно, чтобы поддержка сразу поняла запрос.
    support_text = texts.t(
        'SUPPORT_TOPUP_TEXT',
        '💬 <b>Пополнение через поддержку</b>\n\n'
        'Напишите в поддержку {contact} и укажите ваш ID <code>{user_id}</code>, сумму и удобный способ оплаты.',
    ).format(contact=settings.get_support_contact_display_html(), user_id=html.escape(str(user_id_display)))

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('SUPPORT_TOPUP_WRITE_BUTTON', '💬 Написать в поддержку'),
                    url=settings.get_support_contact_url() or 'https://t.me/',
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='balance_topup')],
        ]
    )

    await callback.message.edit_text(support_text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()


@error_handler
async def process_topup_amount(message: types.Message, db_user: User, state: FSMContext):
    texts = get_texts(db_user.language)

    try:
        if not message.text:
            if message.successful_payment:
                logger.info(
                    'Получено сообщение об успешном платеже без текста, обработчик суммы пополнения завершает работу'
                )
                await state.clear()
                return

            await message.answer(texts.INVALID_AMOUNT, reply_markup=get_back_keyboard(db_user.language))
            return

        amount_text = message.text.strip()
        if not amount_text:
            await message.answer(texts.INVALID_AMOUNT, reply_markup=get_back_keyboard(db_user.language))
            return

        amount_rubles = Decimal(amount_text.replace(',', '.'))
        if not amount_rubles.is_finite():
            await message.answer(texts.INVALID_AMOUNT, reply_markup=get_back_keyboard(db_user.language))
            return

        if amount_rubles < MIN_MANUAL_TOPUP_RUBLES:
            await message.answer(
                format_topup_amount_retry(
                    db_user.language, MIN_MANUAL_TOPUP_RUBLES * 100, MAX_MANUAL_TOPUP_RUBLES * 100, too_low=True
                ),
                reply_markup=get_back_keyboard(db_user.language, callback_data='balance_topup'),
            )
            return

        if amount_rubles > MAX_MANUAL_TOPUP_RUBLES:
            await message.answer(
                format_topup_amount_retry(
                    db_user.language, MIN_MANUAL_TOPUP_RUBLES * 100, MAX_MANUAL_TOPUP_RUBLES * 100, too_low=False
                ),
                reply_markup=get_back_keyboard(db_user.language, callback_data='balance_topup'),
            )
            return

        amount_kopeks = int(amount_rubles * 100)
        data = await state.get_data()
        payment_method = data.get('payment_method', 'stars')

        if not await route_payment_by_method(message, db_user, amount_kopeks, state, payment_method):
            await message.answer(
                texts.t('PAYMENT_METHOD_UNKNOWN', '❌ Этот способ оплаты сейчас недоступен. Выберите другой.'),
                reply_markup=get_back_keyboard(db_user.language, callback_data='balance_topup'),
            )

    except (ValueError, InvalidOperation):
        await message.answer(texts.INVALID_AMOUNT, reply_markup=get_back_keyboard(db_user.language))


async def _reply_after_answer(callback: types.CallbackQuery, text: str, reply_markup=None) -> None:
    """Нажатие уже подтверждено — второй answer() Telegram отвергнет, поэтому пишем сообщением."""
    if isinstance(callback.message, types.Message):
        await callback.message.answer(text, reply_markup=reply_markup)


@error_handler
async def handle_topup_amount_callback(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
):
    try:
        _, method, amount_str = callback.data.split('|', 2)
        amount_kopeks = int(amount_str)
    except ValueError:
        await callback.answer('❌ Некорректный запрос', show_alert=True)
        return

    if amount_kopeks <= 0:
        await callback.answer('❌ Некорректная сумма', show_alert=True)
        return

    if method == 'platega':
        data = await state.get_data()
        if (int(data.get('platega_method', 0)) if data else 0) <= 0:
            from .platega import start_platega_payment

            await state.update_data(platega_pending_amount=amount_kopeks)
            await start_platega_payment(callback, db_user, state)
            return

    # Снимаем «часики» до похода к провайдеру: создание платежа может идти секунды, а Telegram
    # ждёт ответ на нажатие недолго. Поздний answer() падал с «query is too old», собственный
    # except считал это ошибкой пополнения и слал отчёт админам, хотя ссылка на оплату уже ушла.
    await callback.answer()
    try:
        if method.startswith('platega_m'):
            from app.database.database import AsyncSessionLocal

            from .platega import process_platega_payment_amount

            platega_method_code = int(method[len('platega_m') :])
            await state.update_data(payment_method='platega', platega_method=platega_method_code)
            await state.set_state(BalanceStates.waiting_for_amount)
            async with AsyncSessionLocal() as db:
                await process_platega_payment_amount(callback.message, db_user, db, amount_kopeks, state)
        elif method == 'platega':
            # Код способа уже лежит в состоянии — проверено выше.
            from app.database.database import AsyncSessionLocal

            from .platega import process_platega_payment_amount

            await state.set_state(BalanceStates.waiting_for_amount)
            async with AsyncSessionLocal() as db:
                await process_platega_payment_amount(callback.message, db_user, db, amount_kopeks, state)
        # Стандартные методы через роутер
        else:
            await state.update_data(payment_method=method)
            await state.set_state(BalanceStates.waiting_for_amount)
            if not await route_payment_by_method(callback.message, db_user, amount_kopeks, state, method):
                await _reply_after_answer(
                    callback,
                    get_texts(db_user.language).t(
                        'PAYMENT_METHOD_UNKNOWN', '❌ Этот способ оплаты сейчас недоступен. Выберите другой.'
                    ),
                    reply_markup=get_back_keyboard(db_user.language, callback_data='balance_topup'),
                )

    except TelegramBadRequest:
        raise  # устаревший запрос и прочие ответы Telegram классифицирует @error_handler
    except Exception as error:
        logger.error('Ошибка быстрого пополнения', error=error)
        await _reply_after_answer(
            callback,
            '❌ Ошибка обработки запроса',
            reply_markup=get_payment_error_keyboard(db_user.language),
        )


def register_balance_handlers(dp: Dispatcher):
    dp.callback_query.register(show_balance_menu, F.data == 'menu_balance')

    dp.callback_query.register(show_balance_history, F.data == 'balance_history')

    dp.callback_query.register(handle_balance_history_pagination, F.data.startswith('balance_history_page_'))

    dp.callback_query.register(show_payment_methods, F.data == 'balance_topup')
    dp.callback_query.register(show_payment_methods_other_amount, F.data == 'topup_other_amount')

    from .stars import start_stars_payment

    dp.callback_query.register(start_stars_payment, F.data == 'topup_stars')

    from .wata import start_wata_payment

    dp.callback_query.register(start_wata_payment, F.data == 'topup_wata')

    from .platega import handle_platega_method_selection, start_platega_direct_method, start_platega_payment

    dp.callback_query.register(start_platega_payment, F.data == 'topup_platega')
    dp.callback_query.register(
        handle_platega_method_selection,
        F.data.startswith('platega_method_'),
    )
    dp.callback_query.register(
        start_platega_direct_method,
        F.data.regexp(r'^topup_platega_m\d+$'),
    )

    dp.callback_query.register(request_support_topup, F.data == 'topup_support')

    dp.message.register(process_topup_amount, BalanceStates.waiting_for_amount)

    from .cryptobot import start_cryptobot_payment

    dp.callback_query.register(start_cryptobot_payment, F.data == 'topup_cryptobot')

    from .xrocket import start_xrocket_payment

    dp.callback_query.register(start_xrocket_payment, F.data == 'topup_xrocket')

    from .cryptobot import check_cryptobot_payment_status

    dp.callback_query.register(check_cryptobot_payment_status, F.data.startswith('check_cryptobot_'))

    from .xrocket import check_xrocket_payment_status

    dp.callback_query.register(check_xrocket_payment_status, F.data.startswith('check_xrocket_'))

    from .xrocket import select_xrocket_asset

    dp.callback_query.register(select_xrocket_asset, F.data.startswith('xrocket_asset_'))

    from .pay2328 import check_pay2328_payment_status, start_pay2328_payment

    dp.callback_query.register(start_pay2328_payment, F.data == 'topup_pay2328')
    dp.callback_query.register(check_pay2328_payment_status, F.data.startswith('check_pay2328_'))

    from .wata import check_wata_payment_status

    dp.callback_query.register(check_wata_payment_status, F.data.startswith('check_wata_'))

    from .platega import check_platega_payment_status

    dp.callback_query.register(check_platega_payment_status, F.data.startswith('check_platega_'))

    dp.callback_query.register(handle_payment_methods_unavailable, F.data == 'payment_methods_unavailable')

    dp.callback_query.register(handle_topup_amount_callback, F.data.startswith('topup_amount|'))
