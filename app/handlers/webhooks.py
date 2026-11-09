import structlog
from aiogram import Bot, types

from app.config import settings
from app.database.crud.transaction import create_transaction, get_transaction_by_external_id
from app.database.crud.user import add_user_balance, get_user_by_id
from app.database.database import AsyncSessionLocal
from app.database.models import PaymentMethod, TransactionType


logger = structlog.get_logger(__name__)

# Глобальная ссылка на бота для отправки уведомлений
_bot_instance: Bot | None = None


async def handle_successful_payment(message: types.Message):
    try:
        payment = message.successful_payment

        payload_parts = payment.invoice_payload.split('_')
        if len(payload_parts) >= 3 and payload_parts[0] == 'balance':
            user_id = int(payload_parts[1])
            amount_kopeks = int(payload_parts[2])

            async with AsyncSessionLocal() as db:
                try:
                    existing_transaction = await get_transaction_by_external_id(
                        db, payment.telegram_payment_charge_id, PaymentMethod.TELEGRAM_STARS
                    )

                    if existing_transaction:
                        logger.info(
                            'Stars платеж уже обработан', telegram_payment_charge_id=payment.telegram_payment_charge_id
                        )
                        return

                    user = await get_user_by_id(db, user_id)

                    if user:
                        # Атомарно: баланс + единственная DEPOSIT-транзакция с external_id
                        # коммитятся вместе ниже. add_user_balance без своей транзакции и без
                        # самостоятельного коммита — иначе двойная запись + orphan при сбое.
                        await add_user_balance(
                            db,
                            user,
                            amount_kopeks,
                            'Пополнение через Telegram Stars',
                            create_transaction=False,
                            commit=False,
                        )

                        await create_transaction(
                            db=db,
                            user_id=user.id,
                            type=TransactionType.DEPOSIT,
                            amount_kopeks=amount_kopeks,
                            description='Пополнение через Telegram Stars',
                            payment_method=PaymentMethod.TELEGRAM_STARS,
                            external_id=payment.telegram_payment_charge_id,
                            commit=False,
                        )

                        await message.answer(
                            f'✅ Баланс успешно пополнен на {settings.format_price(amount_kopeks)}!\n\n'
                            'Средства зачислены на ваш баланс!'
                        )

                        logger.info(
                            '✅ Обработан Stars платеж', telegram_payment_charge_id=payment.telegram_payment_charge_id
                        )

                    await db.commit()

                except Exception as e:
                    logger.error('Ошибка обработки Stars платежа', error=e)
                    await db.rollback()

    except Exception as e:
        logger.error('Ошибка в обработчике Stars платежа', error=e)


async def handle_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    try:
        await pre_checkout_query.answer(ok=True)
        logger.info('Pre-checkout query принят', pre_checkout_query_id=pre_checkout_query.id)

    except Exception as e:
        logger.error('Ошибка в pre-checkout query', error=e)
        await pre_checkout_query.answer(ok=False, error_message='Ошибка обработки платежа')
