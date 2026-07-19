import html

import structlog
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.keyboards.inline import get_back_keyboard
from app.keyboards.topup_amounts import get_topup_amount_keyboard
from app.localization.texts import get_texts
from app.services.payment_service import PaymentService
from app.states import BalanceStates
from app.utils.decorators import error_handler


logger = structlog.get_logger(__name__)


@error_handler
async def start_xrocket_payment(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    texts = get_texts(db_user.language)

    # Проверка ограничения на пополнение
    if getattr(db_user, 'restriction_topup', False):
        reason = html.escape(getattr(db_user, 'restriction_reason', None) or 'Действие ограничено администратором')
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

    if not settings.is_xrocket_enabled():
        await callback.answer('❌ Оплата криптовалютой временно недоступна', show_alert=True)
        return

    available_assets = settings.get_xrocket_assets()
    assets_text = ', '.join(available_assets)

    message_text = (
        f'🚀 <b>Криптовалюта (xRocket)</b>\n\n'
        f'Введите сумму для пополнения от 100 до 100,000 ₽:\n\n'
        f'💰 Доступные активы: {assets_text}\n'
        f'⚡ Мгновенное зачисление на баланс\n'
        f'🔒 Безопасная оплата через xRocket\n\n'
        f'Курс фиксируется в момент создания счёта.'
    )

    keyboard = await get_topup_amount_keyboard('xrocket', db_user.language, back_callback='back_to_menu')

    await callback.message.edit_text(message_text, reply_markup=keyboard, parse_mode='HTML')

    await state.set_state(BalanceStates.waiting_for_amount)
    await state.update_data(
        payment_method='xrocket',
        xrocket_prompt_message_id=callback.message.message_id,
        xrocket_prompt_chat_id=callback.message.chat.id,
    )
    await callback.answer()


@error_handler
async def process_xrocket_payment_amount(
    message: types.Message, db_user: User, db: AsyncSession, amount_kopeks: int, state: FSMContext
):
    texts = get_texts(db_user.language)

    # Проверка ограничения на пополнение
    if getattr(db_user, 'restriction_topup', False):
        reason = html.escape(getattr(db_user, 'restriction_reason', None) or 'Действие ограничено администратором')
        support_url = settings.get_support_contact_url()
        keyboard = []
        if support_url:
            keyboard.append([types.InlineKeyboardButton(text='🆘 Обжаловать', url=support_url)])
        keyboard.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_balance')])

        await message.answer(
            f'🚫 <b>Пополнение ограничено</b>\n\n{reason}\n\n'
            'Если вы считаете это ошибкой, вы можете обжаловать решение.',
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode='HTML',
        )
        await state.clear()
        return

    texts = get_texts(db_user.language)

    if not settings.is_xrocket_enabled():
        await message.answer('❌ Оплата криптовалютой временно недоступна')
        return

    amount_rubles = amount_kopeks / 100

    if amount_rubles < 100:
        await message.answer('Минимальная сумма пополнения: 100 ₽', reply_markup=get_back_keyboard(db_user.language))
        return

    if amount_rubles > 100000:
        await message.answer(
            'Максимальная сумма пополнения: 100,000 ₽', reply_markup=get_back_keyboard(db_user.language)
        )
        return

    try:
        data = await state.get_data()
        current_rate = data.get('current_rate')

        if not current_rate:
            from app.utils.currency_converter import currency_converter

            current_rate = await currency_converter.get_usd_to_rub_rate()

        amount_usd = amount_rubles / current_rate

        amount_usd = round(amount_usd, 2)

        assets = settings.get_xrocket_assets()

        # Один актив — сразу создаём инвойс. Несколько — даём выбрать.
        if len(assets) > 1:
            rows = []
            for i in range(0, len(assets), 2):
                rows.append(
                    [
                        types.InlineKeyboardButton(
                            text=a, callback_data=f'xrocket_asset_{a}_{amount_kopeks}'
                        )
                        for a in assets[i : i + 2]
                    ]
                )
            rows.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='balance_topup')])

            await message.answer(
                f'🚀 <b>Криптовалюта (xRocket)</b>\n\n'
                f'💰 Сумма к зачислению: {amount_rubles:.0f} ₽\n\n'
                f'Выберите криптовалюту для оплаты:',
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows),
                parse_mode='HTML',
            )
            await state.clear()
            return

        await _create_xrocket_invoice(message, db_user, db, amount_kopeks, assets[0], state)
        return

    except Exception as e:
        logger.error('Ошибка создания xRocket платежа', error=e, exc_info=True)
        await message.answer('❌ Ошибка создания платежа. Попробуйте позже или обратитесь в поддержку.')
        await state.clear()


@error_handler
async def select_xrocket_asset(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    """Пользователь выбрал актив: xrocket_asset_{ASSET}_{kopeks}."""
    try:
        _, _, asset, kopeks_raw = callback.data.split('_', 3)
        amount_kopeks = int(kopeks_raw)
    except (ValueError, AttributeError):
        await callback.answer('❌ Некорректные данные', show_alert=True)
        return

    if asset not in settings.get_xrocket_assets():
        await callback.answer('❌ Актив недоступен', show_alert=True)
        return

    await callback.answer('⏳ Создаю счёт...')
    try:
        await callback.message.delete()
    except Exception:
        pass

    await _create_xrocket_invoice(callback.message, db_user, db, amount_kopeks, asset, state)


async def _create_xrocket_invoice(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    amount_kopeks: int,
    asset: str,
    state: FSMContext,
):
    texts = get_texts(db_user.language)
    amount_rubles = amount_kopeks / 100

    try:
        payment_service = PaymentService(message.bot)

        payment_result = await payment_service.create_xrocket_payment(
            db=db,
            user_id=db_user.id,
            amount_kopeks=amount_kopeks,
            asset=asset,
            description=f'Пополнение баланса на {amount_rubles:.0f} ₽',
            payload=f'balance_{db_user.id}_{amount_kopeks}',
        )

        if not payment_result:
            await message.answer(
                '❌ Не удалось создать платёж.\n\n'
                'Возможно, сумма слишком мала для выбранной криптовалюты. '
                'Попробуйте увеличить сумму, выбрать другой актив или обратиться в поддержку.'
            )
            await state.clear()
            return

        payment_url = payment_result.get('pay_url')

        if not payment_url:
            await message.answer('❌ Ошибка получения ссылки для оплаты. Обратитесь в поддержку.')
            await state.clear()
            return

        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text='🚀 Оплатить', url=payment_url)],
                [
                    types.InlineKeyboardButton(
                        text='📊 Проверить статус',
                        callback_data=f'check_xrocket_{payment_result["local_payment_id"]}',
                    )
                ],
                [types.InlineKeyboardButton(text=texts.BACK, callback_data='balance_topup')],
            ]
        )

        rate = payment_result.get('rate') or 0

        await message.answer(
            f'🚀 <b>Криптовалюта (xRocket)</b>\n\n'
            f'💰 Сумма к зачислению: {amount_rubles:.0f} ₽\n'
            f'🪙 К оплате: {payment_result["amount"]} {payment_result["asset"]}\n'
            f'💱 Курс: 1 {payment_result["asset"]} = {rate:.2f} ₽\n'
            f'🆔 ID платежа: {payment_result["invoice_id"]}\n\n'
            f'📱 <b>Инструкция:</b>\n'
            f"1. Нажмите кнопку 'Оплатить'\n"
            f'2. Подтвердите платёж в @xrocket\n'
            f'3. Деньги поступят на баланс автоматически\n\n'
            f'🔒 Оплата проходит через xRocket\n\n'
            f'❓ Если возникнут проблемы, обратитесь в {settings.get_support_contact_display_html()}',
            reply_markup=keyboard,
            parse_mode='HTML',
        )

        await state.clear()

        logger.info(
            'Создан xRocket платеж',
            telegram_id=db_user.telegram_id,
            amount_rubles=amount_rubles,
            asset=asset,
            invoice_id=payment_result['invoice_id'],
        )

    except Exception as e:
        logger.error('Ошибка создания xRocket платежа', error=e, exc_info=True)
        await message.answer('❌ Ошибка создания платежа. Попробуйте позже или обратитесь в поддержку.')
        await state.clear()


@error_handler
async def check_xrocket_payment_status(callback: types.CallbackQuery, db: AsyncSession):
    try:
        local_payment_id = int(callback.data.split('_')[-1])

        from app.database.crud.xrocket import get_xrocket_payment_by_id

        payment = await get_xrocket_payment_by_id(db, local_payment_id)

        if not payment:
            await callback.answer('❌ Платеж не найден', show_alert=True)
            return

        status_emoji = {'active': '⏳', 'paid': '✅', 'expired': '❌'}

        status_text = {'active': 'Ожидает оплаты', 'paid': 'Оплачен', 'expired': 'Истек'}

        emoji = status_emoji.get(payment.status, '❓')
        status = status_text.get(payment.status, 'Неизвестно')

        message_text = (
            f'🪙 Статус платежа:\n\n'
            f'🆔 ID: {payment.invoice_id[:8]}...\n'
            f'💰 Сумма: {payment.amount} {payment.asset}\n'
            f'📊 Статус: {emoji} {status}\n'
            f'📅 Создан: {payment.created_at.strftime("%d.%m.%Y %H:%M")}\n'
        )

        if payment.is_paid:
            message_text += '\n✅ Платеж успешно завершен!\n\nСредства зачислены на баланс.'
        elif payment.is_pending:
            message_text += "\n⏳ Платеж ожидает оплаты. Нажмите кнопку 'Оплатить' выше."
        elif payment.is_expired:
            message_text += f'\n❌ Платеж истек. Обратитесь в {settings.get_support_contact_display()}'

        await callback.answer(message_text, show_alert=True)

    except Exception as e:
        logger.error('Ошибка проверки статуса xRocket платежа', error=e)
        await callback.answer('❌ Ошибка проверки статуса', show_alert=True)
