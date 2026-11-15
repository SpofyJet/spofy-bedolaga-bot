from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from aiogram import Bot, types
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.promo_group import get_promo_group_by_id
from app.database.crud.subscription import get_subscription_by_user_id
from app.database.crud.transaction import get_user_transactions_count
from app.database.crud.user import (
    add_user_balance,
    get_user_by_id,
    get_users_count,
    get_users_list,
    get_users_statistics,
    subtract_user_balance,
    update_user,
)
from app.database.models import (
    AdvertisingCampaign,
    BroadcastHistory,
    CryptoBotPayment,
    Pay2328Payment,
    PaymentMethod,
    PlategaPayment,
    PromoCode,
    PromoCodeUse,
    PromoGroup,
    ReferralEarning,
    SentNotification,
    Subscription,
    SubscriptionConversion,
    SubscriptionServer,
    Transaction,
    User,
    UserMessage,
    UserStatus,
    WataPayment,
    WelcomeText,
)
from app.localization.texts import get_texts
from app.services.notification_delivery_service import (
    NotificationType,
    notification_delivery_service,
)
from app.utils.notification_keyboards import buy_button


logger = structlog.get_logger(__name__)


@dataclass
class DeleteUserResult:
    """Результат удаления пользователя."""

    bot_deleted: bool = False
    panel_deleted: bool = False
    panel_error: str | None = None


class UserService:
    async def _send_balance_notification(self, bot: Bot, user: User, amount_kopeks: int, admin_name: str) -> bool:
        """
        Отправляет уведомление пользователю о пополнении/списании баланса.
        Поддерживает как Telegram, так и email-only пользователей.
        """
        if amount_kopeks > 0:
            # Пополнение
            emoji = '💰'
            amount_text = f'+{settings.format_price(amount_kopeks)}'
            # Тот же вид, что у пополнений через кассы: «Зачислено N · Баланс M».
            message = f'{emoji} <b>Зачислено {amount_text}</b>\nБаланс: {settings.format_price(user.balance_kopeks)}'
        else:
            # Списание
            emoji = '💸'
            amount_text = f'-{settings.format_price(abs(amount_kopeks))}'
            message = (
                f'{emoji} <b>Списано {amount_text}</b>\n'
                f'Баланс: {settings.format_price(user.balance_kopeks)}\n\n'
                f'Есть вопросы — @spofysup'
            )

        keyboard_rows = []
        subs = user.subscriptions or []
        has_extendable = any(sub.status in {'active', 'expired', 'trial'} for sub in subs)
        if has_extendable:
            keyboard_rows.append(
                [
                    types.InlineKeyboardButton(
                        text=get_texts(user.language).t('SUBSCRIPTION_EXTEND', '💎 Продлить подписку'),
                        callback_data='subscription_extend',
                        style='success',
                    )
                ]
            )

        else:
            keyboard_rows.append([buy_button(get_texts(user.language))])

        reply_markup = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        # Use unified notification delivery service
        context = {
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_kopeks / 100,
            'new_balance_kopeks': user.balance_kopeks,
            'new_balance_rubles': user.balance_kopeks / 100,
            'formatted_amount': settings.format_price(amount_kopeks),
            'formatted_balance': settings.format_price(user.balance_kopeks),
            # No description - don't expose admin name to user
        }

        return await notification_delivery_service.send_notification(
            user=user,
            notification_type=NotificationType.BALANCE_CHANGE,
            context=context,
            bot=bot,
            telegram_message=message,
            telegram_markup=reply_markup,
        )

    async def get_user_profile(self, db: AsyncSession, user_id: int) -> dict[str, Any] | None:
        try:
            user = await get_user_by_id(db, user_id)
            if not user:
                return None

            subscription = await get_subscription_by_user_id(db, user_id)
            transactions_count = await get_user_transactions_count(db, user_id)

            return {
                'user': user,
                'subscription': subscription,
                'transactions_count': transactions_count,
                'is_admin': settings.is_admin(user.telegram_id, user.email),
                'registration_days': (datetime.now(UTC) - user.created_at).days,
            }

        except Exception as e:
            logger.error('Ошибка получения профиля пользователя', user_id=user_id, error=e)
            return None

    async def search_users(self, db: AsyncSession, query: str, page: int = 1, limit: int = 20) -> dict[str, Any]:
        try:
            offset = (page - 1) * limit

            users = await get_users_list(db, offset=offset, limit=limit, search=query)
            total_count = await get_users_count(db, search=query)

            total_pages = (total_count + limit - 1) // limit

            return {
                'users': users,
                'current_page': page,
                'total_pages': total_pages,
                'total_count': total_count,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            }

        except Exception as e:
            logger.error('Ошибка поиска пользователей', error=e)
            return {
                'users': [],
                'current_page': 1,
                'total_pages': 1,
                'total_count': 0,
                'has_next': False,
                'has_prev': False,
            }

    async def get_users_page(
        self,
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        status: UserStatus | None = None,
        order_by_balance: bool = False,
        order_by_traffic: bool = False,
        order_by_last_activity: bool = False,
        order_by_total_spent: bool = False,
        order_by_purchase_count: bool = False,
    ) -> dict[str, Any]:
        try:
            offset = (page - 1) * limit

            users = await get_users_list(
                db,
                offset=offset,
                limit=limit,
                status=status,
                order_by_balance=order_by_balance,
                order_by_traffic=order_by_traffic,
                order_by_last_activity=order_by_last_activity,
                order_by_total_spent=order_by_total_spent,
                order_by_purchase_count=order_by_purchase_count,
            )
            total_count = await get_users_count(db, status=status)

            total_pages = (total_count + limit - 1) // limit

            return {
                'users': users,
                'current_page': page,
                'total_pages': total_pages,
                'total_count': total_count,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            }

        except Exception as e:
            logger.error('Ошибка получения страницы пользователей', error=e)
            return {
                'users': [],
                'current_page': 1,
                'total_pages': 1,
                'total_count': 0,
                'has_next': False,
                'has_prev': False,
            }

    async def update_user_balance(
        self,
        db: AsyncSession,
        user_id: int,
        amount_kopeks: int,
        description: str,
        admin_id: int,
        bot: Bot | None = None,
        admin_name: str | None = None,
    ) -> bool:
        try:
            user = await get_user_by_id(db, user_id)
            if not user:
                return False

            # Сохраняем старый баланс для уведомления

            if amount_kopeks > 0:
                await add_user_balance(
                    db, user, amount_kopeks, description=description, payment_method=PaymentMethod.MANUAL
                )
                logger.info(
                    'Админ пополнил баланс пользователя на ₽',
                    admin_id=admin_id,
                    user_id=user_id,
                    amount_kopeks=amount_kopeks / 100,
                )
                success = True
            else:
                success = await subtract_user_balance(
                    db,
                    user,
                    abs(amount_kopeks),
                    description,
                    create_transaction=True,
                    payment_method=PaymentMethod.MANUAL,
                )
                if success:
                    logger.info(
                        'Админ списал с баланса пользователя ₽',
                        admin_id=admin_id,
                        user_id=user_id,
                        value=abs(amount_kopeks) / 100,
                    )

            # Отправляем уведомление пользователю, если операция прошла успешно
            if success and bot:
                # Обновляем пользователя для получения нового баланса
                await db.refresh(user)

                # Получаем имя администратора
                if not admin_name:
                    admin_user = await get_user_by_id(db, admin_id)
                    admin_name = admin_user.full_name if admin_user else f'Админ #{admin_id}'

                # Отправляем уведомление (не блокируем операцию если не удалось отправить)
                await self._send_balance_notification(bot, user, amount_kopeks, admin_name)

            return success

        except Exception as e:
            logger.error('Ошибка изменения баланса пользователя', error=e)
            return False

    async def update_user_promo_group(
        self, db: AsyncSession, user_id: int, promo_group_id: int
    ) -> tuple[bool, User | None, PromoGroup | None, PromoGroup | None]:
        try:
            user = await get_user_by_id(db, user_id)
            if not user:
                return False, None, None, None

            old_group = user.promo_group

            promo_group = await get_promo_group_by_id(db, promo_group_id)
            if not promo_group:
                return False, None, None, old_group

            user.promo_group_id = promo_group.id
            user.promo_group = promo_group
            user.updated_at = datetime.now(UTC)

            await db.commit()
            await db.refresh(user)

            logger.info(
                '👥 Промогруппа пользователя обновлена',
                telegram_id=user.telegram_id,
                promo_group_name=promo_group.name,
            )

            return True, user, promo_group, old_group

        except Exception as e:
            await db.rollback()
            logger.error('Ошибка обновления промогруппы пользователя', user_id=user_id, error=e)
            return False, None, None, None

    async def block_user(
        self, db: AsyncSession, user_id: int, admin_id: int, reason: str = 'Заблокирован администратором'
    ) -> bool:
        try:
            user = await get_user_by_id(db, user_id)
            if not user:
                return False

            from app.services.rbac_bootstrap_service import is_protected_from_blocking

            if is_protected_from_blocking(user):
                logger.warning(
                    'Отказ в блокировке: аккаунт прописан в ADMIN_IDS/ADMIN_EMAILS',
                    admin_id=admin_id,
                    user_id=user_id,
                )
                return False

            from app.database.crud.subscription import deactivate_subscription, is_active_paid_subscription

            subs = user.subscriptions or []
            has_active_paid = any(is_active_paid_subscription(sub) for sub in subs)

            if has_active_paid:
                logger.info(
                    '⏭️ Пропуск отключения RemnaWave и подписки: у пользователя активная оплаченная подписка',
                    user_id=user_id,
                    remnawave_id=user.remnawave_id,
                )
            else:
                from app.services.subscription_service import SubscriptionService

                subscription_service = SubscriptionService()

                if user.remnawave_id:
                    try:
                        await subscription_service.disable_remnawave_user(user.remnawave_id)
                        logger.info(
                            '✅ RemnaWave пользователь деактивирован при блокировке',
                            remnawave_id=user.remnawave_id,
                        )
                    except Exception as e:
                        logger.error('❌ Ошибка деактивации RemnaWave пользователя при блокировке', error=e)

                for sub in subs:
                    if sub.status in ['active', 'trial']:
                        await deactivate_subscription(db, sub)

            await update_user(db, user, status=UserStatus.BLOCKED.value)

            logger.info('Админ заблокировал пользователя', admin_id=admin_id, user_id=user_id, reason=reason)
            return True

        except Exception as e:
            logger.error('Ошибка блокировки пользователя', error=e)
            return False

    async def unblock_user(self, db: AsyncSession, user_id: int, admin_id: int) -> bool:
        try:
            user = await get_user_by_id(db, user_id)
            if not user:
                return False

            await update_user(db, user, status=UserStatus.ACTIVE.value)

            from app.database.models import SubscriptionStatus

            now = datetime.now(UTC)
            for sub in user.subscriptions or []:
                if sub.end_date and sub.end_date > now and sub.status != SubscriptionStatus.ACTIVE.value:
                    sub.status = SubscriptionStatus.ACTIVE.value
                    try:
                        from app.services.subscription_service import SubscriptionService

                        subscription_service = SubscriptionService()
                        await subscription_service.update_remnawave_user(db, sub)
                        logger.info(
                            '✅ RemnaWave подписка восстановлена при разблокировке',
                            subscription_id=sub.id,
                            remnawave_id=user.remnawave_id,
                        )
                    except Exception as e:
                        logger.error(
                            '❌ Ошибка восстановления RemnaWave подписки при разблокировке',
                            subscription_id=sub.id,
                            error=e,
                        )
                        from app.services.remnawave_retry_queue import remnawave_retry_queue

                        if hasattr(sub, 'id') and hasattr(sub, 'user_id'):
                            remnawave_retry_queue.enqueue(
                                subscription_id=sub.id,
                                user_id=sub.user_id,
                                action='update',
                            )
            await db.commit()

            logger.info('Админ разблокировал пользователя', admin_id=admin_id, user_id=user_id)
            return True

        except Exception as e:
            logger.error('Ошибка разблокировки пользователя', error=e)
            return False

    async def delete_user_account(
        self, db: AsyncSession, user_id: int, admin_id: int, *, force_panel_delete: bool = False
    ) -> DeleteUserResult:
        """Полное удаление пользователя из бота и (опционально) из панели RemnaWave.

        force_panel_delete=True: пропускает проверку активной подписки и принудительно
        удаляет (не деактивирует) пользователя из панели RemnaWave. Используется
        при полном удалении через кабинет администратора.
        """
        result = DeleteUserResult()
        try:
            user = await get_user_by_id(db, user_id)
            if not user:
                logger.warning('Пользователь не найден для удаления', user_id=user_id)
                return result

            user_id_display = user.telegram_id or user.email or f'#{user.id}'
            logger.info('🗑️ Начинаем полное удаление пользователя', user_id=user_id, user_id_display=user_id_display)

            from app.config import settings
            from app.database.crud.subscription import is_active_paid_subscription

            # Collect all panel user ids to process
            subs = user.subscriptions or []

            panel_user_ids = [user.remnawave_id] if user.remnawave_id else []

            if panel_user_ids:
                if not force_panel_delete and any(is_active_paid_subscription(sub) for sub in subs):
                    logger.info(
                        '⏭️ Пропуск отключения RemnaWave при удалении: у пользователя активная оплаченная подписка',
                        user_id=user_id,
                    )
                else:
                    delete_mode = 'delete' if force_panel_delete else settings.get_remnawave_user_delete_mode()

                    # Помечаем ВСЕ панельные id до цикла, чтобы webhook от первого
                    # удаления не пришёл раньше чем помечены остальные
                    if delete_mode == 'delete':
                        from app.services.remnawave_webhook_service import RemnaWaveWebhookService

                        RemnaWaveWebhookService.mark_intentional_panel_deletion(
                            panel_user_ids=panel_user_ids,
                            telegram_id=int(user.telegram_id) if user.telegram_id else None,
                        )

                    for panel_user_id in panel_user_ids:
                        try:
                            from app.services.remnawave_service import RemnaWaveService

                            remnawave_service = RemnaWaveService()

                            if delete_mode == 'delete':
                                async with remnawave_service.get_api_client() as api:
                                    # 3.0.0: DELETE отвечает 204/202 без тела, поля isDeleted
                                    # больше нет — успех это отсутствие исключения.
                                    await api.delete_user(panel_user_id)
                                    result.panel_deleted = True
                                    logger.info(
                                        '✅ RemnaWave пользователь удален из панели',
                                        remnawave_id=panel_user_id,
                                    )
                            else:
                                from app.services.subscription_service import SubscriptionService

                                subscription_service = SubscriptionService()
                                disabled = await subscription_service.disable_remnawave_user(panel_user_id)
                                result.panel_deleted = disabled
                                if disabled:
                                    logger.info(
                                        '✅ RemnaWave пользователь деактивирован',
                                        remnawave_id=panel_user_id,
                                        delete_mode=delete_mode,
                                    )
                                else:
                                    result.panel_error = 'disable_remnawave_user вернул False'
                                    logger.warning(
                                        '⚠️ Не удалось деактивировать пользователя в RemnaWave',
                                        remnawave_id=panel_user_id,
                                        delete_mode=delete_mode,
                                    )

                        except Exception as e:
                            from app.external.remnawave_api import RemnaWaveAPIError, is_user_not_found_error

                            # Панель уже не знает такого пользователя — цель достигнута.
                            # Fallback-деактивация по несуществующему id гарантированно
                            # провалится и покажет админу ошибку на успешном удалении.
                            # RemnaWaveInvalidUserIdError сюда НЕ попадает (битая ссылка
                            # в БД бота — не «пользователя нет»), уходит в общую ветку.
                            if isinstance(e, RemnaWaveAPIError) and is_user_not_found_error(e):
                                result.panel_deleted = True
                                logger.info(
                                    'ℹ️ RemnaWave пользователь уже отсутствует в панели',
                                    remnawave_id=panel_user_id,
                                    delete_mode=delete_mode,
                                )
                                continue

                            result.panel_error = 'Ошибка обработки пользователя в Remnawave'
                            logger.warning(
                                '⚠️ Ошибка обработки пользователя в Remnawave',
                                delete_mode=delete_mode,
                                remnawave_id=panel_user_id,
                                error=e,
                            )
                            if delete_mode == 'delete':
                                try:
                                    from app.services.subscription_service import SubscriptionService

                                    subscription_service = SubscriptionService()
                                    disabled = await subscription_service.disable_remnawave_user(panel_user_id)
                                    if disabled:
                                        result.panel_deleted = True
                                        result.panel_error = 'Удаление не удалось, пользователь деактивирован'
                                        logger.info(
                                            '✅ RemnaWave пользователь деактивирован как fallback',
                                            remnawave_id=panel_user_id,
                                        )
                                except Exception as fallback_e:
                                    logger.error('❌ Ошибка деактивации RemnaWave как fallback', fallback_e=fallback_e)

            try:
                async with db.begin_nested():
                    sent_notifications_result = await db.execute(
                        select(SentNotification).where(SentNotification.user_id == user_id)
                    )
                    sent_notifications = sent_notifications_result.scalars().all()

                    if sent_notifications:
                        logger.info('🔄 Удаляем уведомлений', sent_notifications_count=len(sent_notifications))
                        await db.execute(delete(SentNotification).where(SentNotification.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления уведомлений', error=e)

            try:
                async with db.begin_nested():
                    user_messages_result = await db.execute(
                        update(UserMessage).where(UserMessage.created_by == user_id).values(created_by=None)
                    )
                    if user_messages_result.rowcount > 0:
                        logger.info('🔄 Обновлено пользовательских сообщений', rowcount=user_messages_result.rowcount)
                    await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка обновления пользовательских сообщений', error=e)

            try:
                async with db.begin_nested():
                    promocodes_result = await db.execute(
                        update(PromoCode).where(PromoCode.created_by == user_id).values(created_by=None)
                    )
                    if promocodes_result.rowcount > 0:
                        logger.info('🔄 Обновлено промокодов', rowcount=promocodes_result.rowcount)
                    await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка обновления промокодов', error=e)

            try:
                async with db.begin_nested():
                    welcome_texts_result = await db.execute(
                        update(WelcomeText).where(WelcomeText.created_by == user_id).values(created_by=None)
                    )
                    if welcome_texts_result.rowcount > 0:
                        logger.info('🔄 Обновлено приветственных текстов', rowcount=welcome_texts_result.rowcount)
                    await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка обновления приветственных текстов', error=e)

            try:
                async with db.begin_nested():
                    referrals_result = await db.execute(
                        update(User).where(User.referred_by_id == user_id).values(referred_by_id=None)
                    )
                    if referrals_result.rowcount > 0:
                        logger.info('🔗 Очищены реферальные ссылки у рефералов', rowcount=referrals_result.rowcount)
                    await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка очистки реферальных ссылок', error=e)

            try:
                async with db.begin_nested():
                    cryptobot_result = await db.execute(
                        select(CryptoBotPayment).where(CryptoBotPayment.user_id == user_id)
                    )
                    cryptobot_payments = cryptobot_result.scalars().all()

                    if cryptobot_payments:
                        logger.info('🔄 Удаляем CryptoBot платежей', cryptobot_payments_count=len(cryptobot_payments))
                        await db.execute(
                            update(CryptoBotPayment)
                            .where(CryptoBotPayment.user_id == user_id)
                            .values(transaction_id=None)
                        )
                        await db.flush()
                        await db.execute(delete(CryptoBotPayment).where(CryptoBotPayment.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления CryptoBot платежей', error=e)

            try:
                async with db.begin_nested():
                    platega_result = await db.execute(select(PlategaPayment).where(PlategaPayment.user_id == user_id))
                    platega_payments = platega_result.scalars().all()

                    if platega_payments:
                        logger.info('🔄 Удаляем Platega платежей', platega_payments_count=len(platega_payments))
                        await db.execute(
                            update(PlategaPayment).where(PlategaPayment.user_id == user_id).values(transaction_id=None)
                        )
                        await db.flush()
                        await db.execute(delete(PlategaPayment).where(PlategaPayment.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления Platega платежей', error=e)

            try:
                async with db.begin_nested():
                    pay2328_result = await db.execute(select(Pay2328Payment).where(Pay2328Payment.user_id == user_id))
                    pay2328_payments = pay2328_result.scalars().all()

                    if pay2328_payments:
                        logger.info('🔄 Удаляем 2328.io платежей', pay2328_payments_count=len(pay2328_payments))
                        await db.execute(
                            update(Pay2328Payment).where(Pay2328Payment.user_id == user_id).values(transaction_id=None)
                        )
                        await db.flush()
                        await db.execute(delete(Pay2328Payment).where(Pay2328Payment.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления 2328.io платежей', error=e)

            # Удаляем Wata платежи (до транзакций, т.к. wata_payments.transaction_id -> transactions.id)
            try:
                async with db.begin_nested():
                    wata_payments_result = await db.execute(select(WataPayment).where(WataPayment.user_id == user_id))
                    wata_payments = wata_payments_result.scalars().all()

                    if wata_payments:
                        logger.info('🔄 Удаляем Wata платежей', wata_payments_count=len(wata_payments))
                        await db.execute(
                            update(WataPayment).where(WataPayment.user_id == user_id).values(transaction_id=None)
                        )
                        await db.flush()
                        await db.execute(delete(WataPayment).where(WataPayment.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления Wata платежей', error=e)

            try:
                async with db.begin_nested():
                    transactions_result = await db.execute(select(Transaction).where(Transaction.user_id == user_id))
                    transactions = transactions_result.scalars().all()

                    if transactions:
                        logger.info('🔄 Удаляем транзакций', transactions_count=len(transactions))
                        await db.execute(delete(Transaction).where(Transaction.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления транзакций', error=e)

            try:
                async with db.begin_nested():
                    promocode_uses_result = await db.execute(
                        select(PromoCodeUse).where(PromoCodeUse.user_id == user_id)
                    )
                    promocode_uses = promocode_uses_result.scalars().all()

                    if promocode_uses:
                        logger.info('🔄 Удаляем использований промокодов', promocode_uses_count=len(promocode_uses))
                        await db.execute(delete(PromoCodeUse).where(PromoCodeUse.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления использований промокодов', error=e)

            try:
                async with db.begin_nested():
                    referral_earnings_result = await db.execute(
                        select(ReferralEarning).where(ReferralEarning.user_id == user_id)
                    )
                    referral_earnings = referral_earnings_result.scalars().all()

                    if referral_earnings:
                        logger.info('🔄 Удаляем реферальных доходов', referral_earnings_count=len(referral_earnings))
                        await db.execute(delete(ReferralEarning).where(ReferralEarning.user_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления реферальных доходов', error=e)

            try:
                async with db.begin_nested():
                    referral_records_result = await db.execute(
                        select(ReferralEarning).where(ReferralEarning.referral_id == user_id)
                    )
                    referral_records = referral_records_result.scalars().all()

                    if referral_records:
                        logger.info('🔄 Удаляем записей о рефералах', referral_records_count=len(referral_records))
                        await db.execute(delete(ReferralEarning).where(ReferralEarning.referral_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления записей о рефералах', error=e)

            try:
                async with db.begin_nested():
                    conversions_result = await db.execute(
                        select(SubscriptionConversion).where(SubscriptionConversion.user_id == user_id)
                    )
                    conversions = conversions_result.scalars().all()

                    if conversions:
                        logger.info('🔄 Удаляем записей конверсий', conversions_count=len(conversions))
                        await db.execute(
                            delete(SubscriptionConversion).where(SubscriptionConversion.user_id == user_id)
                        )
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления записей конверсий', error=e)

            try:
                async with db.begin_nested():
                    broadcast_history_result = await db.execute(
                        select(BroadcastHistory).where(BroadcastHistory.admin_id == user_id)
                    )
                    broadcast_history = broadcast_history_result.scalars().all()

                    if broadcast_history:
                        logger.info(
                            '🔄 Удаляем записей истории рассылок', broadcast_history_count=len(broadcast_history)
                        )
                        await db.execute(delete(BroadcastHistory).where(BroadcastHistory.admin_id == user_id))
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка удаления истории рассылок', error=e)

            try:
                async with db.begin_nested():
                    campaigns_result = await db.execute(
                        select(AdvertisingCampaign).where(AdvertisingCampaign.created_by == user_id)
                    )
                    campaigns = campaigns_result.scalars().all()

                    if campaigns:
                        logger.info('🔄 Очищаем создателя у рекламных кампаний', campaigns_count=len(campaigns))
                        await db.execute(
                            update(AdvertisingCampaign)
                            .where(AdvertisingCampaign.created_by == user_id)
                            .values(created_by=None)
                        )
                        await db.flush()
            except Exception as e:
                logger.error('❌ Ошибка обновления рекламных кампаний', error=e)

            try:
                async with db.begin_nested():
                    subs = user.subscriptions or []
                    if subs:
                        all_squad_ids: set[str] = set()
                        for sub in subs:
                            logger.info('🔄 Удаляем подписку', subscription_id=sub.id)
                            if sub.connected_squads:
                                all_squad_ids.update(sub.connected_squads)
                            await db.execute(
                                delete(SubscriptionServer).where(SubscriptionServer.subscription_id == sub.id)
                            )

                        # Delete all subscriptions for this user
                        # Lock order: subscriptions -> server_squads (matches webhook order)
                        await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
                        await db.flush()

                        # Decrement server_squads.current_users AFTER subscription delete
                        # to match lock ordering with webhook and avoid deadlocks
                        if all_squad_ids:
                            try:
                                from app.database.crud.server_squad import (
                                    get_server_ids_by_uuids,
                                    remove_user_from_servers,
                                )

                                int_squad_ids = await get_server_ids_by_uuids(db, list(all_squad_ids))
                                if int_squad_ids:
                                    await remove_user_from_servers(db, int_squad_ids)
                            except Exception as sq_err:
                                logger.warning('⚠️ Не удалось уменьшить счётчик серверов', error=sq_err)
            except Exception as e:
                logger.error('❌ Ошибка удаления подписок', error=e)

            try:
                from app.database.models import AccessPolicy, AdminAuditLog, AdminRole, UserRole, WithdrawalRequest

                await db.execute(delete(AdminAuditLog).where(AdminAuditLog.user_id == user_id))
                await db.execute(delete(WithdrawalRequest).where(WithdrawalRequest.user_id == user_id))
                await db.execute(
                    update(WithdrawalRequest).where(WithdrawalRequest.processed_by == user_id).values(processed_by=None)
                )
                await db.execute(update(AdminRole).where(AdminRole.created_by == user_id).values(created_by=None))
                await db.execute(update(UserRole).where(UserRole.assigned_by == user_id).values(assigned_by=None))
                await db.execute(update(AccessPolicy).where(AccessPolicy.created_by == user_id).values(created_by=None))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
                logger.info('✅ Пользователь окончательно удален из базы', user_id=user_id)
            except Exception as e:
                logger.error('❌ Ошибка финального удаления пользователя', error=e)
                await db.rollback()
                return result

            result.bot_deleted = True
            logger.info(
                '✅ Пользователь полностью удалён администратором',
                user_id_display=user_id_display,
                user_id=user_id,
                admin_id=admin_id,
            )
            return result

        except Exception as e:
            logger.error('❌ Критическая ошибка удаления пользователя', user_id=user_id, error=e)
            await db.rollback()
            return result

    async def get_user_statistics(self, db: AsyncSession) -> dict[str, Any]:
        try:
            stats = await get_users_statistics(db)
            return stats

        except Exception as e:
            logger.error('Ошибка получения статистики пользователей', error=e)
            return {
                'total_users': 0,
                'active_users': 0,
                'blocked_users': 0,
                'new_today': 0,
                'new_week': 0,
                'new_month': 0,
            }
