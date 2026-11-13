# trial_message_cleaned_v2: duplicated welcome-tip blocks removed (20260810-170510)
import html
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InaccessibleMessage, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.subscription import (
    create_paid_subscription,
    create_trial_subscription,
)
from app.database.models import PaymentMethod, Subscription, SubscriptionStatus, User
from app.keyboards.inline import (
    get_back_keyboard,
    get_happ_download_button_row,
    get_insufficient_balance_keyboard,
    get_payment_methods_keyboard_with_cart,
    get_subscription_keyboard,
    get_updated_subscription_settings_keyboard,
)
from app.localization.texts import Texts, get_texts
from app.middlewares.banner_variant import show_banner_state
from app.services.admin_notification_service import AdminNotificationService
from app.services.pricing_engine import pricing_engine
from app.services.remnawave_service import RemnaWaveConfigurationError
from app.services.subscription_auto_purchase_service import ADDON_CART_MODES
from app.services.subscription_service import SubscriptionService
from app.services.trial_activation_service import revert_trial_activation
from app.services.user_cart_service import user_cart_service
from app.utils.formatters import format_human_datetime
from app.utils.legacy_subscription import is_legacy_subscription as _legacy_subscription


logger = structlog.get_logger(__name__)


async def _resolve_subscription(callback, db_user, db, state=None):
    """Resolve subscription — delegates to shared resolve_subscription_from_context."""
    from .common import resolve_subscription_from_context

    return await resolve_subscription_from_context(callback, db_user, db, state)


def _serialize_markup(markup: InlineKeyboardMarkup | None) -> Any | None:
    if markup is None:
        return None

    model_dump = getattr(markup, 'model_dump', None)
    if callable(model_dump):
        try:
            return model_dump(exclude_none=True)
        except TypeError:
            return model_dump()

    to_python = getattr(markup, 'to_python', None)
    if callable(to_python):
        return to_python()

    return markup


from app.states import SubscriptionStates
from app.utils.lifetime import is_lifetime_end
from app.utils.subscription_time import format_expiry_warning, format_time_left
from app.utils.subscription_utils import (
    get_display_subscription_link,
    resolve_simple_subscription_device_limit,
)
from app.utils.timezone import format_local_datetime, to_local_datetime

from .autopay import (
    handle_autopay_menu,
    handle_sbp_recurring_cancel,
    handle_sbp_recurring_cancel_confirm,
    handle_sbp_recurring_enable,
    handle_sbp_recurring_enable_for,
    handle_sbp_recurring_menu,
    handle_subscription_cancel,
    set_autopay_days,
    set_autopay_period,
    show_autopay_days,
    show_autopay_period,
    toggle_autopay,
)
from .common import update_traffic_prices
from .countries import (
    _should_show_countries_management,
    apply_countries_changes,
    handle_add_countries,
    handle_manage_country,
)
from .devices import (
    confirm_add_devices,
    confirm_change_devices,
    confirm_reset_devices,
    execute_change_devices,
    get_current_devices_count,
    get_servers_display_names,
    handle_all_devices_reset_from_management,
    handle_app_selection,
    handle_change_devices,
    handle_device_guide,
    handle_device_management,
    handle_devices_page,
    handle_reset_devices,
    handle_single_device_reset,
    handle_specific_app_guide,
    show_device_connection_help,
)
from .happ import (
    handle_happ_download_back,
    handle_happ_download_close,
    handle_happ_download_platform_choice,
    handle_happ_download_request,
)
from .links import handle_connect_subscription, handle_open_subscription_link
from .promo import claim_discount_offer, handle_promo_offer_close
from .traffic import (
    confirm_reset_traffic,
    confirm_switch_traffic,
    execute_switch_traffic,
    handle_no_traffic_packages,
    handle_reset_traffic,
    handle_switch_traffic,
)


async def show_subscription_info(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # Multi-tariff: redirect to "My subscriptions" list
    if settings.is_multi_tariff_enabled():
        from app.handlers.subscription.my_subscriptions import show_my_subscriptions

        await show_my_subscriptions(callback, db_user, db)
        return

    # Проверяем, доступно ли сообщение для редактирования
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    await db.refresh(db_user)

    texts = get_texts(db_user.language)
    gift_enabled = True
    # Multi-tariff: this branch is only reached in single-tariff mode (multi-tariff
    # is redirected to show_my_subscriptions above). db_user.subscription returns
    # the first active or most recent subscription, which is correct here.
    subscription = db_user.subscription

    if not subscription:
        await callback.message.edit_text(
            texts.SUBSCRIPTION_NONE,
            reply_markup=get_subscription_keyboard(db_user.language, has_subscription=False, gift_enabled=gift_enabled),
        )
        await callback.answer()
        return

    from app.database.crud.subscription import check_and_update_subscription_status

    subscription = await check_and_update_subscription_status(db, subscription)

    subscription_service = SubscriptionService()
    await subscription_service.sync_subscription_usage(db, subscription)

    # Панель не ответила — дальше к ней не ходим, экран собирается из базы. При сбое 02.11.2026
    # запросов было до четырёх подряд (трафик, проверка, устройства и ещё раз устройства), каждый
    # до двух минут: человек ждал экран минутами, а соединение с базой за это время обрывалось.
    if subscription_service.panel_failed:
        logger.warning('Панель не отвечает: «Моя подписка» показана по данным базы', subscription_id=subscription.id)
    else:
        # Проверяем и синхронизируем подписку с RemnaWave если необходимо
        sync_success, sync_error = await subscription_service.ensure_subscription_synced(db, subscription)
        if not sync_success:
            logger.warning(
                'Не удалось синхронизировать подписку с RemnaWave',
                subscription_id=subscription.id,
                sync_error=sync_error,
            )

    await db.refresh(subscription)
    await db.refresh(db_user)

    current_time = datetime.now(UTC)

    if subscription.status == 'limited':
        actual_status = 'limited'
        status_display = texts.t('SUBSCRIPTION_STATUS_LIMITED', 'Трафик исчерпан')
        status_emoji = '⚠️'
    elif subscription.status == 'disabled':
        actual_status = 'disabled'
        status_display = texts.t('SUBSCRIPTION_STATUS_DISABLED', 'Приостановлена')
        status_emoji = '⏸️'
    elif subscription.status == 'expired' or subscription.end_date <= current_time:
        actual_status = 'expired'
        status_display = texts.t('SUBSCRIPTION_STATUS_EXPIRED', 'Истекла')
        status_emoji = '🔴'
    elif subscription.status == 'active' and subscription.end_date > current_time:
        if subscription.is_trial:
            actual_status = 'trial_active'
            status_display = texts.t('SUBSCRIPTION_STATUS_TRIAL', 'Тестовая')
            status_emoji = '🎯'
        else:
            actual_status = 'paid_active'
            status_display = texts.t('SUBSCRIPTION_STATUS_ACTIVE', 'Активна')
            status_emoji = '💎'
    else:
        actual_status = 'unknown'
        status_display = texts.t('SUBSCRIPTION_STATUS_UNKNOWN', 'Неизвестно')
        status_emoji = '❓'

    time_left_text = format_time_left(texts, subscription.end_date, current_time)
    warning_text = format_expiry_warning(texts, subscription.end_date, current_time)

    subscription_type = (
        texts.t('SUBSCRIPTION_TYPE_TRIAL', 'Триал')
        if subscription.is_trial
        else texts.t('SUBSCRIPTION_TYPE_PAID', 'Платная')
    )

    # Снапшот лимита мог разойтись с тарифом (тариф редактировали после
    # покупки) — лечим из живого тарифа ДО отображения, иначе на безлимитном
    # тарифе пользователь видит «0.0 / 100 ГБ», а панель реально режет трафик.
    try:
        from app.database.crud.subscription import reconcile_subscription_traffic_limit

        _rec_fixed, _rec_total = await reconcile_subscription_traffic_limit(db, subscription)
        if _rec_fixed:
            await db.commit()
    except Exception as _rec_err:
        logger.warning('Не удалось сверить лимит трафика подписки с тарифом', error=_rec_err)

    used_traffic = f'{subscription.traffic_used_gb:.1f}'
    from app.services.bypass_downgrade import has_bypass_quota, is_suspension_effective

    if has_bypass_quota(subscription):
        # Лимит — квота только на обходы: обычные ноды трафик не считают.
        traffic_used_display = texts.t(
            'SUBSCRIPTION_TRAFFIC_BYPASS_QUOTA',
            'без лимита на обычных серверах\n🏴‍☠️ Обходы: {used} / {limit} ГБ',
        ).format(used=used_traffic, limit=subscription.traffic_limit_gb)
        if is_suspension_effective(subscription):
            traffic_used_display += texts.t('SUBSCRIPTION_TRAFFIC_BYPASS_OFF_SUFFIX', ' — отключены')
    elif subscription.traffic_limit_gb == 0:
        traffic_used_display = texts.t(
            'SUBSCRIPTION_TRAFFIC_UNLIMITED',
            '∞ (безлимит) | Использовано: {used} ГБ',
        ).format(used=used_traffic)
    else:
        traffic_used_display = texts.t(
            'SUBSCRIPTION_TRAFFIC_LIMITED',
            '{used} / {limit} ГБ',
        ).format(used=used_traffic, limit=subscription.traffic_limit_gb)

    devices_used_str = '—'
    devices_list = []
    devices_count = 0

    show_devices = settings.is_devices_selection_enabled()
    devices_used_str = ''
    devices_list: list[dict[str, Any]] = []

    if show_devices and subscription_service.panel_failed:
        devices_used_str = '—'
    elif show_devices:
        try:
            _device_panel_id = (
                getattr(subscription, 'remnawave_id', None)
                if settings.is_multi_tariff_enabled() and subscription
                else None
            ) or db_user.remnawave_id
            if _device_panel_id:
                from app.services.remnawave_service import RemnaWaveService

                service = RemnaWaveService()

                async with service.get_api_client() as api:
                    devices_info = await api.get_user_devices(_device_panel_id)

                    if isinstance(devices_info, dict):
                        devices_count = devices_info.get('total', 0)
                        devices_list = devices_info.get('devices', [])
                        devices_used_str = str(devices_count)
                        logger.info(
                            'Найдено устройств для пользователя',
                            devices_count=devices_count,
                            telegram_id=db_user.telegram_id,
                        )
                    else:
                        logger.warning(
                            'Не удалось получить информацию об устройствах для', telegram_id=db_user.telegram_id
                        )

        except Exception as e:
            # Повторять тот же запрос (get_current_devices_count) незачем: он упадёт так же.
            logger.error('Ошибка получения устройств для отображения', error=e)
            devices_used_str = '—'

    servers_names = await get_servers_display_names(subscription.connected_squads)
    servers_display = servers_names or texts.t('SUBSCRIPTION_NO_SERVERS', 'Нет серверов')

    # Получаем информацию о тарифе для режима тарифов
    tariff_info_block = ''
    tariff = None
    if subscription.tariff_id:
        try:
            from app.database.crud.tariff import get_tariff_by_id

            tariff = await get_tariff_by_id(db, subscription.tariff_id)
            if tariff:
                # Прикрепляем тариф к подписке для использования в клавиатуре
                subscription.tariff = tariff

                # Формируем блок информации о тарифе
                is_daily = getattr(tariff, 'is_daily', False)
                tariff_type_str = '🔄 Суточный' if is_daily else '📅 Периодный'

                # Трафик и устройства ниже уже показаны в блоке подписки — здесь только название.
                tariff_info_lines = [f'<b>{html.escape(tariff.name)}</b>']
                if is_daily:
                    tariff_info_lines.append(f'Тип: {tariff_type_str}')

                if is_daily:
                    # Для суточного тарифа показываем цену с учётом скидки промогруппы + promo-offer
                    raw_daily_kopeks = getattr(tariff, 'daily_price_kopeks', 0)
                    promo_group = (
                        db_user.get_primary_promo_group() if hasattr(db_user, 'get_primary_promo_group') else None
                    )
                    daily_group_pct = promo_group.get_discount_percent('period', 1) if promo_group else 0
                    from app.services.pricing_engine import PricingEngine
                    from app.utils.promo_offer import get_user_active_promo_discount_percent

                    daily_offer_pct = get_user_active_promo_discount_percent(db_user)
                    if daily_group_pct > 0 or daily_offer_pct > 0:
                        daily_kopeks, _, _ = PricingEngine.apply_stacked_discounts(
                            raw_daily_kopeks, daily_group_pct, daily_offer_pct
                        )
                    else:
                        daily_kopeks = raw_daily_kopeks
                    daily_price = daily_kopeks / 100
                    tariff_info_lines.append(f'Цена: {daily_price:.2f} ₽/день')

                    # Прогресс-бар до следующего списания
                    last_charge = getattr(subscription, 'last_daily_charge_at', None)
                    is_paused = getattr(subscription, 'is_daily_paused', False)

                    if is_paused:
                        tariff_info_lines.append('')
                        tariff_info_lines.append('⏸️ <b>Подписка приостановлена</b>')
                        # Показываем оставшееся время даже при паузе
                        if last_charge:
                            next_charge = last_charge + timedelta(hours=24)
                            now = datetime.now(UTC)
                            if next_charge > now:
                                time_until = next_charge - now
                                hours_left = time_until.seconds // 3600
                                minutes_left = (time_until.seconds % 3600) // 60
                                tariff_info_lines.append(f'⏳ Осталось: {hours_left}ч {minutes_left}мин')
                                tariff_info_lines.append('💤 Списание приостановлено')
                    elif last_charge:
                        next_charge = last_charge + timedelta(hours=24)
                        now = datetime.now(UTC)

                        if next_charge > now:
                            time_until = next_charge - now
                            hours_left = time_until.seconds // 3600
                            minutes_left = (time_until.seconds % 3600) // 60

                            # Процент оставшегося времени (24 часа = 100%)
                            total_seconds = 24 * 3600
                            remaining_seconds = time_until.total_seconds()
                            percent = min(100, max(0, (remaining_seconds / total_seconds) * 100))

                            # Генерируем прогресс-бар
                            bar_length = 10
                            filled = int(bar_length * percent / 100)
                            empty = bar_length - filled
                            progress_bar = '▓' * filled + '░' * empty

                            tariff_info_lines.append('')
                            tariff_info_lines.append(f'⏳ До списания: {hours_left}ч {minutes_left}мин')
                            tariff_info_lines.append(f'[{progress_bar}] {percent:.0f}%')
                    else:
                        tariff_info_lines.append('')
                        tariff_info_lines.append('⏳ Первое списание скоро')

                if len(tariff_info_lines) == 1:
                    tariff_info_block = '\n' + tariff_info_lines[0]
                else:
                    tariff_info_block = '\n<blockquote expandable>' + '\n'.join(tariff_info_lines) + '</blockquote>'

        except Exception as e:
            logger.warning('Ошибка получения тарифа', error=e, exc_info=True)

    # n4: строка автопродления для платных подписок (на триале недоступно)
    autopay_line = ''
    if not subscription.is_trial and actual_status in ('paid_active', 'limited'):
        try:
            from app.services.recurrent_amount import get_active_recurrent_engines

            engines = await get_active_recurrent_engines(db, subscription)
            engine_names = {
                'platega': texts.t('RECURRENT_ENGINE_SBP', 'СБП'),
                'balance': texts.t('RECURRENT_ENGINE_BALANCE', 'с баланса'),
            }
            active_engines = [engine_names[e] for e in ('platega', 'balance') if e in engines]
            if active_engines:
                autopay_line = '\n' + texts.t(
                    'SUBSCRIPTION_AUTOPAY_ON', '💳 Автопродление: включено ({engine})'
                ).format(engine=', '.join(active_engines))
            else:
                autopay_line = '\n' + texts.t('SUBSCRIPTION_AUTOPAY_OFF', '💳 Автопродление: выключено')
        except Exception as e:
            logger.warning('Не удалось определить статус автопродления', error=e)

    # Определяем, суточный ли тариф для выбора шаблона
    is_daily_tariff = tariff and getattr(tariff, 'is_daily', False)

    if is_daily_tariff:
        # Для суточных тарифов другой шаблон без "Действует до" и "Осталось"
        message_template = texts.t(
            'SUBSCRIPTION_DAILY_OVERVIEW_TEMPLATE',
            """👤 <b>{full_name}</b>
💰 Баланс: <b>{balance}</b>

{status_emoji} <b>Подписка:</b> {status_display}{warning}{tariff_info_block}{autopay_line}

<blockquote>📈 Трафик: {traffic}
📱 Устройства: {devices_used} / {device_limit}</blockquote>""",
        )
    else:
        message_template = texts.t(
            'SUBSCRIPTION_OVERVIEW_TEMPLATE',
            """👤 <b>{full_name}</b>
💰 Баланс: <b>{balance}</b>

{status_emoji} <b>Подписка:</b> {status_display}{warning}{tariff_info_block}{autopay_line}

<blockquote>📅 Действует до: {end_date}
⏳ Осталось: {time_left}
📈 Трафик: {traffic}
📱 Устройства: {devices_used} / {device_limit}</blockquote>""",
        )

    if not show_devices:
        # n4: строку устройств убираем по плейсхолдеру — работает для любой
        # локали (старый replace по русскому тексту молча не срабатывал
        # на английском); закрывающий тег цитаты переносим на строку выше.
        _tpl_lines = []
        for _tpl_line in message_template.split('\n'):
            if '{devices_used}' in _tpl_line:
                if '</blockquote>' in _tpl_line and _tpl_lines:
                    _tpl_lines[-1] += '</blockquote>'
                continue
            _tpl_lines.append(_tpl_line)
        message_template = '\n'.join(_tpl_lines)

    if is_lifetime_end(subscription.end_date):
        # Бессрочная (ULTIMA): вместо «Действует до: 31.12.2099 / Осталось: 26 000 дн.»
        # одна строка «Срок: навсегда». По плейсхолдерам — работает в любой локали.
        _lifetime_line = texts.t(
            'SUBSCRIPTION_OVERVIEW_LIFETIME_LINE',
            "<tg-emoji emoji-id='5908972566537572230'>♾️</tg-emoji> Срок: <b>навсегда</b>",
        )
        _tpl_lines = []
        for _tpl_line in message_template.split('\n'):
            if '{time_left}' in _tpl_line and '{end_date}' not in _tpl_line:
                continue
            if '{end_date}' in _tpl_line:
                _prefix = '<blockquote>' if '<blockquote>' in _tpl_line else ''
                _suffix = '</blockquote>' if '</blockquote>' in _tpl_line else ''
                _tpl_line = f'{_prefix}{_lifetime_line}{_suffix}'
            _tpl_lines.append(_tpl_line)
        message_template = '\n'.join(_tpl_lines)

    device_limit_display = Texts.format_device_limit(subscription.device_limit)

    message = message_template.format(
        full_name=html.escape(db_user.full_name or ''),
        balance=settings.format_price(db_user.balance_kopeks),
        status_emoji=status_emoji,
        status_display=status_display,
        warning=warning_text,
        tariff_info_block=tariff_info_block,
        autopay_line=autopay_line,
        subscription_type=subscription_type,
        end_date=format_human_datetime(to_local_datetime(subscription.end_date), db_user.language),
        time_left=time_left_text,
        traffic=traffic_used_display,
        servers=servers_display,
        devices_used=devices_used_str,
        device_limit=device_limit_display,
    )

    if show_devices and devices_list:
        message += '\n\n' + texts.t(
            'SUBSCRIPTION_CONNECTED_DEVICES_TITLE',
            '<blockquote>📱 <b>Подключенные устройства:</b>\n',
        )
        for device in devices_list[:5]:
            platform = device.get('platform', 'Unknown')
            device_model = device.get('deviceModel', 'Unknown')
            device_info = f'{platform} - {device_model}'

            if len(device_info) > 35:
                device_info = device_info[:32] + '...'
            message += f'• {device_info}\n'
        message += texts.t('SUBSCRIPTION_CONNECTED_DEVICES_FOOTER', '</blockquote>')

    # Отображаем докупленный трафик
    if subscription.traffic_limit_gb > 0:  # Только для лимитированных тарифов
        from sqlalchemy import select as sql_select

        from app.database.models import TrafficPurchase

        now = datetime.now(UTC)
        purchases_query = (
            sql_select(TrafficPurchase)
            .where(TrafficPurchase.subscription_id == subscription.id)
            .where(TrafficPurchase.expires_at > now)
            .order_by(TrafficPurchase.expires_at.asc())
        )
        purchases_result = await db.execute(purchases_query)
        purchases = purchases_result.scalars().all()

        if purchases:
            message += '\n\n' + texts.t(
                'SUBSCRIPTION_PURCHASED_TRAFFIC_TITLE',
                '<blockquote>📦 <b>Докупленный трафик:</b>\n',
            )

            for purchase in purchases:
                time_remaining = purchase.expires_at - now
                days_remaining = max(0, int(time_remaining.total_seconds() / 86400))

                # Генерируем прогресс-бар
                total_duration_seconds = (purchase.expires_at - purchase.created_at).total_seconds()
                elapsed_seconds = (now - purchase.created_at).total_seconds()
                progress_percent = min(
                    100.0,
                    max(0.0, (elapsed_seconds / total_duration_seconds * 100) if total_duration_seconds > 0 else 0),
                )

                bar_length = 10
                filled = int((progress_percent / 100) * bar_length)
                bar = '▰' * filled + '▱' * (bar_length - filled)

                # Форматируем дату истечения
                expire_date = format_local_datetime(purchase.expires_at, '%d.%m.%Y')

                # Формируем текст о времени
                if days_remaining == 0:
                    time_text = 'истекает сегодня'
                elif days_remaining == 1:
                    time_text = 'остался 1 день'
                elif days_remaining < 5:
                    time_text = f'осталось {days_remaining} дня'
                else:
                    time_text = f'осталось {days_remaining} дней'

                message += f'• {purchase.traffic_gb} ГБ — {time_text}\n'
                message += f'  {bar} {progress_percent:.0f}% | до {expire_date}\n'

            message += texts.t('SUBSCRIPTION_PURCHASED_TRAFFIC_FOOTER', '</blockquote>')

    subscription_link = get_display_subscription_link(subscription)
    hide_subscription_link = settings.should_hide_subscription_link()

    if subscription_link and actual_status in ['trial_active', 'paid_active'] and not hide_subscription_link:
        subscription_link_display = subscription_link

        if settings.is_happ_cryptolink_mode():
            subscription_link_display = f'<blockquote expandable><code>{subscription_link}</code></blockquote>'
        else:
            subscription_link_display = f'<code>{subscription_link}</code>'

        message += '\n\n' + texts.t(
            'SUBSCRIPTION_CONNECT_LINK_SECTION',
            '🔗 <b>Ссылка для подключения:</b>\n{subscription_url}',
        ).format(subscription_url=subscription_link_display)
        message += '\n\n' + texts.t(
            'SUBSCRIPTION_CONNECT_LINK_PROMPT',
            '📱 Скопируйте ссылку и добавьте в ваше VPN приложение',
        )

    await callback.message.edit_text(
        message,
        reply_markup=get_subscription_keyboard(
            db_user.language,
            has_subscription=True,
            is_trial=subscription.is_trial,
            subscription=subscription,
            gift_enabled=gift_enabled,
        ),
        parse_mode='HTML',
    )
    await callback.answer()


async def show_trial_offer(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # Проверяем, доступно ли сообщение для редактирования
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)

    # Триал отключён глобально (нулевая длительность) либо для этого типа пользователя
    if settings.TRIAL_DURATION_DAYS <= 0 or settings.is_trial_disabled_for_user(db_user.auth_type):
        await callback.message.edit_text(
            texts.t('TRIAL_DISABLED_FOR_USER_TYPE', 'Пробный период недоступен'),
            reply_markup=get_back_keyboard(db_user.language),
        )
        await callback.answer()
        return

    # Проверяем, использовал ли пользователь триал
    # PENDING триальные подписки не считаются - пользователь может повторить оплату
    # Multi-tariff note: db_user.subscription returns the first active/most recent
    # subscription. In multi-tariff mode a user can have multiple subscriptions, but
    # trial eligibility is still "has any subscription" so this check is correct.
    if db_user.is_trial_already_used():
        # smart-trial-button: вместо тупика сразу ведём на покупку
        trial_used_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy', style='success')],
                [InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')],
            ]
        )
        await callback.message.edit_text(texts.TRIAL_ALREADY_USED, reply_markup=trial_used_keyboard)
        await callback.answer()
        return

    # Бесплатный пробный период включается одним нажатием: экран «Активировать?» только добавлял шаг,
    # а условия (срок, обходы, устройства) человек видит в сообщении после активации.
    await activate_trial(callback, db_user, db)


def _trial_activated_text(texts, subscription=None) -> str:
    """«Доступ активирован до …» + что в него входит, если в пробном есть обходы.

    Подсказка «+2 дня за друга» отсюда переехала в сообщение после первого подключения: здесь
    главное — подключиться, а не звать друзей.
    """
    text = texts.TRIAL_ACTIVATED
    end_date = getattr(subscription, 'end_date', None)
    if end_date is not None:
        text += '\n' + texts.t('TRIAL_ACTIVATED_UNTIL', '📅 До {end_date}').format(
            end_date=format_local_datetime(end_date, '%d.%m, %H:%M')
        )
    if settings.BYPASS_INCLUDE_TRIAL and (settings.TRIAL_TRAFFIC_LIMIT_GB or 0) > 0:
        text += '\n\n' + texts.t(
            'TRIAL_ACTIVATED_BYPASS_NOTE',
            '📶 Обычные серверы — без лимита.\n🏴‍☠️ На серверы «Обход» — {gb} ГБ.',
        ).format(gb=settings.TRIAL_TRAFFIC_LIMIT_GB)
    return text


def _trial_next_steps_text(texts) -> str:
    return texts.t(
        'TRIAL_NEXT_STEPS',
        'Осталось два шага:\n1. Скачать приложение\n2. Нажать «Добавить подписку»\n\n'
        'Оба — на одной странице, кнопка ниже 👇',
    )


def _trial_help_row(texts) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=texts.t('TRIAL_HELP_BUTTON', '💬 Не получается? Поможем'),
            callback_data='menu_support',
        )
    ]


async def activate_trial(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)

    # Проверка ограничения на покупку/продление подписки
    if db_user.restriction_subscription:
        reason = html.escape(db_user.restriction_reason or 'Действие ограничено администратором')
        support_url = settings.get_support_contact_url()
        keyboard = []
        if support_url:
            keyboard.append([types.InlineKeyboardButton(text='🆘 Обжаловать', url=support_url)])
        keyboard.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')])

        await callback.message.edit_text(
            f'🚫 <b>Активация подписки ограничена</b>\n\n{reason}\n\n'
            'Если вы считаете это ошибкой, вы можете обжаловать решение.',
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
        )
        await callback.answer()
        return

    # Триал отключён глобально (нулевая длительность) либо для этого типа пользователя
    if settings.TRIAL_DURATION_DAYS <= 0 or settings.is_trial_disabled_for_user(db_user.auth_type):
        await callback.message.edit_text(
            texts.t('TRIAL_DISABLED_FOR_USER_TYPE', 'Пробный период недоступен'),
            reply_markup=get_back_keyboard(db_user.language),
        )
        await callback.answer()
        return

    # Проверяем, использовал ли пользователь триал
    # PENDING триальные подписки не считаются - пользователь может повторить оплату
    # Multi-tariff note: db_user.subscription returns the first active/most recent
    # subscription. Trial eligibility is "has any subscription" so this check is correct.
    if db_user.is_trial_already_used():
        # smart-trial-button: вместо тупика сразу ведём на покупку
        trial_used_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy', style='success')],
                [InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')],
            ]
        )
        await callback.message.edit_text(texts.TRIAL_ALREADY_USED, reply_markup=trial_used_keyboard)
        await callback.answer()
        return

    # Проверяем, платный ли триал
    subscription: Subscription | None = None
    remnawave_user = None

    try:
        forced_devices = None
        if not settings.is_devices_selection_enabled():
            forced_devices = settings.get_disabled_mode_device_limit()

        # Проверяем, настроен ли триальный тариф для режима тарифов
        trial_tariff = None
        trial_traffic_limit = None
        trial_device_limit = forced_devices
        trial_squads = None
        tariff_id_for_trial = None
        trial_duration = None  # None = использовать TRIAL_DURATION_DAYS

        try:
            from app.database.crud.tariff import get_tariff_by_id, get_trial_tariff

            # Сначала проверяем тариф из БД с флагом is_trial_available
            # Триальный тариф может быть неактивным — используется для отдельных лимитов
            trial_tariff = await get_trial_tariff(db)

            # Если не найден в БД, проверяем настройку TRIAL_TARIFF_ID
            if not trial_tariff:
                trial_tariff_id = settings.get_trial_tariff_id()
                if trial_tariff_id > 0:
                    trial_tariff = await get_tariff_by_id(db, trial_tariff_id)

            if trial_tariff:
                from app.database.crud.server_squad import get_effective_tariff_squad_uuids

                trial_traffic_limit = trial_tariff.traffic_limit_gb
                trial_device_limit = trial_tariff.device_limit
                trial_squads = await get_effective_tariff_squad_uuids(db, trial_tariff.allowed_squads)
                tariff_id_for_trial = trial_tariff.id
                tariff_trial_days = getattr(trial_tariff, 'trial_duration_days', None)
                if tariff_trial_days:
                    trial_duration = tariff_trial_days
                logger.info(
                    'Используем триальный тариф (ID: )',
                    trial_tariff_name=trial_tariff.name,
                    trial_tariff_id=trial_tariff.id,
                )
        except Exception as e:
            logger.error('Ошибка получения триального тарифа', error=e)

        # No trial tariff configured, use the legacy random trial squad fallback.
        if not trial_squads:
            from app.database.crud.server_squad import get_random_trial_squad_uuid

            trial_squad_uuid = await get_random_trial_squad_uuid(db)
            trial_squads = [trial_squad_uuid] if trial_squad_uuid else []

        from app.services.checkout_squad_validation import CheckoutSquadsUnavailableError, validate_checkout_squads

        try:
            await validate_checkout_squads(trial_squads)
        except CheckoutSquadsUnavailableError as error:
            await callback.message.edit_text(texts.t('TARIFF_SERVERS_UNAVAILABLE', error.message))
            await callback.answer()
            return

        subscription = await create_trial_subscription(
            db,
            db_user.id,
            duration_days=trial_duration,
            device_limit=trial_device_limit,
            traffic_limit_gb=trial_traffic_limit,
            connected_squads=trial_squads,
            tariff_id=tariff_id_for_trial,
        )

        await db.refresh(db_user)

        subscription_service = SubscriptionService()
        try:
            remnawave_user = await subscription_service.create_remnawave_user(
                db,
                subscription,
            )
        except RemnaWaveConfigurationError as error:
            logger.error('RemnaWave update skipped due to configuration error', error=error)
            revert_result = await revert_trial_activation(db, db_user, subscription)
            if not revert_result.subscription_rolled_back:
                failure_text = texts.t(
                    'TRIAL_ROLLBACK_FAILED',
                    'Не удалось отменить активацию триала после ошибки списания. Свяжитесь с поддержкой и попробуйте позже.',
                )
                failure_text = texts.t(
                    'TRIAL_PROVISIONING_FAILED',
                    'Не удалось завершить активацию триала. Средства возвращены на баланс. Попробуйте позже.',
                )

            await callback.message.edit_text(
                failure_text,
                reply_markup=get_back_keyboard(db_user.language),
            )
            await callback.answer()
            return
        except Exception as error:
            logger.error(
                'Failed to create RemnaWave user for trial subscription',
                getattr=getattr(subscription, 'id', '<unknown>'),
                error=error,
            )
            revert_result = await revert_trial_activation(db, db_user, subscription)
            if not revert_result.subscription_rolled_back:
                failure_text = texts.t(
                    'TRIAL_ROLLBACK_FAILED',
                    'Не удалось отменить активацию триала после ошибки списания. Свяжитесь с поддержкой и попробуйте позже.',
                )
                failure_text = texts.t(
                    'TRIAL_PROVISIONING_FAILED',
                    'Не удалось завершить активацию триала. Средства возвращены на баланс. Попробуйте позже.',
                )

            await callback.message.edit_text(
                failure_text,
                reply_markup=get_back_keyboard(db_user.language),
            )
            await callback.answer()
            return

        await db.refresh(db_user)

        try:
            notification_service = AdminNotificationService(callback.bot)
            await notification_service.send_trial_activation_notification(db, db_user, subscription)
        except Exception as e:
            logger.error('Ошибка отправки уведомления о триале', error=e)

        subscription_link = get_display_subscription_link(subscription)
        hide_subscription_link = settings.should_hide_subscription_link()
        # Экран успеха — уже под баннером пробного периода, а не «2 дня бесплатно».
        show_banner_state(db_user, 'trial')

        payment_note = ''

        if remnawave_user and subscription_link:
            if settings.is_happ_cryptolink_mode():
                trial_success_text = (
                    f'{_trial_activated_text(texts, subscription)}\n\n'
                    + texts.t(
                        'SUBSCRIPTION_HAPP_LINK_PROMPT',
                        '🔒 Ссылка на подписку создана. Нажмите кнопку "Подключиться" ниже, чтобы открыть её в Happ.',
                    )
                    + '\n\n'
                    + texts.t(
                        'SUBSCRIPTION_IMPORT_INSTRUCTION_PROMPT',
                        '📱 Нажмите кнопку ниже, чтобы получить инструкцию по настройке VPN на вашем устройстве',
                    )
                )
            elif hide_subscription_link:
                trial_success_text = (
                    f'{_trial_activated_text(texts, subscription)}\n\n'
                    + texts.t(
                        'SUBSCRIPTION_LINK_HIDDEN_NOTICE',
                        'ℹ️ Ссылка подписки доступна по кнопкам ниже или в разделе "Моя подписка".',
                    )
                    + '\n\n'
                    + texts.t(
                        'SUBSCRIPTION_IMPORT_INSTRUCTION_PROMPT',
                        '📱 Нажмите кнопку ниже, чтобы получить инструкцию по настройке VPN на вашем устройстве',
                    )
                )
            else:
                # Сырая ссылка тут не нужна: человеку осталось два шага, и оба — на странице по кнопке.
                # Ссылка для ручного ввода остаётся на экране «Подписка».
                trial_success_text = f'{_trial_activated_text(texts, subscription)}\n\n{_trial_next_steps_text(texts)}'

            trial_success_text += payment_note

            connect_mode = settings.CONNECT_BUTTON_MODE

            if connect_mode == 'miniapp_subscription':
                connect_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'),
                                web_app=types.WebAppInfo(url=subscription_link),
                                style='success',
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'),
                                callback_data='back_to_menu',
                            )
                        ],
                    ]
                )
            elif connect_mode == 'miniapp_custom':
                if not settings.MINIAPP_CUSTOM_URL:
                    await callback.answer(
                        texts.t(
                            'CUSTOM_MINIAPP_URL_NOT_SET',
                            '⚠ Кастомная ссылка для мини-приложения не настроена',
                        ),
                        show_alert=True,
                    )
                    return

                connect_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'),
                                web_app=types.WebAppInfo(url=settings.MINIAPP_CUSTOM_URL),
                                style='success',
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'),
                                callback_data='back_to_menu',
                            )
                        ],
                    ]
                )
            elif connect_mode == 'link':
                rows = [
                    [
                        InlineKeyboardButton(
                            text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'),
                            url=subscription_link,
                            style='success',
                        )
                    ]
                ]
                happ_row = get_happ_download_button_row(texts)
                if happ_row:
                    rows.append(happ_row)
                rows.append(_trial_help_row(texts))
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'),
                            callback_data='back_to_menu',
                        )
                    ]
                )
                connect_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            elif connect_mode == 'happ_cryptolink':
                rows = [
                    [
                        InlineKeyboardButton(
                            text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'),
                            callback_data='open_subscription_link',
                            style='success',
                        )
                    ]
                ]
                happ_row = get_happ_download_button_row(texts)
                if happ_row:
                    rows.append(happ_row)
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'),
                            callback_data='back_to_menu',
                        )
                    ]
                )
                connect_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            else:
                connect_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'),
                                callback_data='subscription_connect',
                                style='success',
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'),
                                callback_data='back_to_menu',
                            )
                        ],
                    ]
                )

            await callback.message.edit_text(
                trial_success_text,
                reply_markup=connect_keyboard,
                parse_mode='HTML',
            )
        else:
            trial_success_text = f'{_trial_activated_text(texts, subscription)}\n\n⚠️ Ссылка генерируется, откройте «Подписку» через несколько секунд.'
            trial_success_text += payment_note
            await callback.message.edit_text(
                trial_success_text,
                reply_markup=get_back_keyboard(db_user.language),
            )

        logger.info('✅ Активирована тестовая подписка для пользователя', telegram_id=db_user.telegram_id)

    except Exception as e:
        logger.error('Ошибка активации триала', error=e)
        failure_text = texts.ERROR

        if subscription and remnawave_user is None:
            revert_result = await revert_trial_activation(db, db_user, subscription)
            if not revert_result.subscription_rolled_back:
                failure_text = texts.t(
                    'TRIAL_ROLLBACK_FAILED',
                    'Не удалось отменить активацию триала после ошибки списания. Свяжитесь с поддержкой и попробуйте позже.',
                )
                failure_text = texts.t(
                    'TRIAL_PROVISIONING_FAILED',
                    'Не удалось завершить активацию триала. Средства возвращены на баланс. Попробуйте позже.',
                )

        await callback.message.edit_text(failure_text, reply_markup=get_back_keyboard(db_user.language))
        await callback.answer()
        return

    await callback.answer()


async def start_subscription_purchase(
    callback: types.CallbackQuery,
    state: FSMContext,
    db_user: User,
    db: AsyncSession,
):
    get_texts(db_user.language)

    # Проверяем режим продаж - если tariffs, перенаправляем на выбор тарифов
    from .tariff_purchase import show_tariffs_list

    await show_tariffs_list(callback, db_user, db, state)


async def save_cart_and_redirect_to_topup(
    callback: types.CallbackQuery, state: FSMContext, db_user: User, missing_amount: int
):
    texts = get_texts(db_user.language)
    data = await state.get_data()

    # Сохраняем данные корзины в Redis
    cart_data = {
        **data,
        'saved_cart': True,
        'missing_amount': missing_amount,
        'return_to_cart': True,
        'user_id': db_user.id,
    }

    await user_cart_service.save_user_cart(db_user.id, cart_data)

    await callback.message.edit_text(
        f'💰 Недостаточно средств для оформления подписки\n\n'
        f'Требуется: {texts.format_price(missing_amount, round_kopeks=False)}\n'
        f'У вас: {texts.format_price(db_user.balance_kopeks, round_kopeks=False)}\n\n'
        f'🛒 Ваша корзина сохранена!\n'
        f'После пополнения баланса вы сможете вернуться к оформлению подписки.\n\n'
        f'Выберите способ пополнения:',
        reply_markup=get_payment_methods_keyboard_with_cart(
            db_user.language,
            missing_amount,
        ),
        parse_mode='HTML',
    )


async def return_to_saved_cart(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    # Получаем данные корзины из Redis
    cart_data = await user_cart_service.get_user_cart(db_user.id)

    if not cart_data:
        await callback.answer('❌ Сохраненная корзина не найдена', show_alert=True)
        return

    get_texts(db_user.language)

    # Проверяем режим корзины - если это тарифная корзина, перенаправляем на соответствующий обработчик
    cart_mode = cart_data.get('cart_mode')
    if cart_mode in ('tariff_purchase', 'daily_tariff_purchase', 'extend') and cart_data.get('tariff_id'):
        from .tariff_purchase import return_to_saved_tariff_cart

        await return_to_saved_tariff_cart(callback, state, db_user, db, cart_data)
        return

    # Докупка трафика/устройств — не подписка: у такой корзины нет period_days,
    # и общая ветка ниже объявляла её «повреждённой» и удаляла.
    if cart_mode in ADDON_CART_MODES:
        from .addon_cart import resume_addon_cart_from_button

        await resume_addon_cart_from_button(callback, db_user, db, cart_data)
        return

    await callback.answer('❌ Корзина устарела. Оформите подписку заново', show_alert=True)
    await user_cart_service.delete_user_cart(db_user.id)


async def handle_extend_subscription(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext = None,
):
    # Проверяем, доступно ли сообщение для редактирования
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)

    if settings.is_multi_tariff_enabled():
        subscription, _sub_id = await _resolve_subscription(callback, db_user, db, state)
        if subscription is None:
            return
    else:
        subscription = db_user.subscription

    if not subscription:
        await callback.message.edit_text(
            '🎯 <b>Пробный период заканчивается</b>\n\nЧтобы продолжить пользоваться VPN, выберите подходящий тариф.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy', style='success'
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('WEBHOOK_CLOSE_BUTTON', '✖️ Закрыть'),
                            callback_data='webhook:close',
                        )
                    ],
                ]
            ),
            parse_mode='HTML',
        )
        await callback.answer()
        return

    if not subscription.is_trial and is_lifetime_end(subscription.end_date):
        # ULTIMA «Навсегда»: продлевать нечего (кнопка скрыта, это старые сообщения).
        await callback.answer(
            texts.t('SUBSCRIPTION_LIFETIME_NO_RENEW', '♾️ Подписка действует навсегда — продлевать не нужно.'),
            show_alert=True,
        )
        return

    # Триальная подписка с тарифом — направляем на покупку этого тарифа
    if subscription.is_trial:
        if subscription.tariff_id:
            from .tariff_purchase import show_tariff_extend

            await show_tariff_extend(callback, db_user, db)
            return
        # Триал без тарифа — предлагаем выбрать
        await callback.message.edit_text(
            '🎯 <b>Пробный период заканчивается</b>\n\nЧтобы продолжить пользоваться VPN, выберите подходящий тариф.',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text=texts.MENU_BUY_SUBSCRIPTION, callback_data='menu_buy', style='success'
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text=texts.t('WEBHOOK_CLOSE_BUTTON', '✖️ Закрыть'),
                            callback_data='webhook:close',
                        )
                    ],
                ]
            ),
            parse_mode='HTML',
        )
        await callback.answer()
        return

    # Подписка с тарифом — всегда используем тарифный flow,
    # даже если бот в классическом режиме (подписка могла быть куплена через кабинет)
    if subscription.tariff_id:
        # Проверяем, суточный ли тариф — у суточных нет period_prices, продление через resume
        from app.database.crud.tariff import get_tariff_by_id

        tariff = await get_tariff_by_id(db, subscription.tariff_id)
        if tariff and tariff.is_daily:
            # Суточный тариф: перенаправляем на страницу подписки (там кнопка «Возобновить»)
            await show_subscription_info(callback, db_user, db)
            return

        if tariff:
            # У подписки есть тариф - перенаправляем на продление по тарифу
            from .tariff_purchase import show_tariff_extend

            await show_tariff_extend(callback, db_user, db)
            return

    # У подписки нет тарифа, но режим тарифов включён - предлагаем выбрать тариф
    await callback.message.edit_text(
        '📦 <b>Выберите тариф для продления</b>\n\n'
        'Ваша текущая подписка была создана до введения тарифов.\n'
        'Для продления необходимо выбрать один из доступных тарифов.\n\n'
        '⚠️ Ваша текущая подписка продолжит действовать до окончания срока.',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t('MOVE_TO_TARIFF_BUTTON', '📦 Перейти на тариф'),
                        callback_data='tariff_switch',
                    )
                ],
                [types.InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')],
            ]
        ),
        parse_mode='HTML',
    )
    await callback.answer()
    return


async def confirm_extend_subscription(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None
):
    if not callback.data:
        await callback.answer('⚠ Ошибка данных', show_alert=True)
        return
    int(callback.data.split('_')[2])
    texts = get_texts(db_user.language)

    # Block classic subscription renewal when tariff mode is active
    await callback.answer(
        texts.t('TARIFF_MODE_RENEWAL_BLOCKED', '❌ Продление в этом режиме недоступно. Выберите тариф.'),
        show_alert=True,
    )
    return

    # Валидация что период доступен для продления


async def create_paid_subscription_with_traffic_mode(
    db: AsyncSession,
    user_id: int,
    duration_days: int,
    device_limit: int | None,
    connected_squads: list[str],
    traffic_gb: int | None = None,
    autopay_enabled: bool | None = None,
):
    from app.config import settings

    if traffic_gb is None:
        if settings.is_traffic_fixed():
            traffic_limit_gb = settings.get_fixed_traffic_limit()
        else:
            traffic_limit_gb = 0
    else:
        traffic_limit_gb = traffic_gb

    create_kwargs = dict(
        db=db,
        user_id=user_id,
        duration_days=duration_days,
        traffic_limit_gb=traffic_limit_gb,
        connected_squads=connected_squads,
        update_server_counters=False,
    )

    if device_limit is not None:
        create_kwargs['device_limit'] = device_limit

    if autopay_enabled is not None:
        create_kwargs['autopay_enabled'] = autopay_enabled

    subscription = await create_paid_subscription(**create_kwargs)

    logger.info(
        '📋 Создана подписка с трафиком: ГБ (режим: )',
        traffic_limit_gb=traffic_limit_gb,
        TRAFFIC_SELECTION_MODE=settings.TRAFFIC_SELECTION_MODE,
    )

    return subscription


async def handle_subscription_settings(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # Проверяем, доступно ли сообщение для редактирования
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)

    if settings.is_multi_tariff_enabled():
        await callback.answer('Настройки доступны через "Мои подписки"', show_alert=True)
        return

    subscription = db_user.subscription

    # Получаем тариф подписки если есть
    tariff = None
    if subscription and subscription.tariff_id:
        from app.database.crud.tariff import get_tariff_by_id

        tariff = await get_tariff_by_id(db, subscription.tariff_id)

    if not subscription or subscription.is_trial:  # trial-nav-fix: гейт возвращён
        await callback.answer(
            texts.t(
                'SUBSCRIPTION_SETTINGS_PAID_ONLY',
                '⚠️ Настройки доступны только для платных подписок',
            ),
            show_alert=True,
        )
        return

    # В режиме тарифов отдельного экрана «Настройки» нет: устройства, их количество и перевыпуск ссылки
    # вынесены на экран подписки, а все старые «Назад» (devices.py, revoke.py) ведут сюда, к нему.
    if tariff is not None:
        await show_subscription_info(callback, db_user, db)
        return

    show_devices = settings.is_devices_selection_enabled()

    if show_devices:
        devices_used = await get_current_devices_count(db_user)
    else:
        devices_used = 0

    settings_template = texts.t(
        'SUBSCRIPTION_SETTINGS_OVERVIEW',
        (
            '⚙️ <b>Настройки подписки</b>\n\n'
            '📊 <b>Текущие параметры:</b>\n'
            '🌐 Стран: {countries_count}\n'
            '📈 Трафик: {traffic_used} / {traffic_limit}\n'
            '📱 Устройства: {devices_used} / {devices_limit}\n\n'
            'Выберите что хотите изменить:'
        ),
    )

    if not show_devices:
        settings_template = settings_template.replace(
            '\n📱 Устройства: {devices_used} / {devices_limit}',
            '',
        )

    devices_limit_display = Texts.format_device_limit(subscription.device_limit)

    settings_text = settings_template.format(
        countries_count=len(subscription.connected_squads or []),
        traffic_used=texts.format_traffic(subscription.traffic_used_gb, is_limit=False),
        traffic_limit=texts.format_traffic(subscription.traffic_limit_gb, is_limit=True),
        devices_used=devices_used,
        devices_limit=devices_limit_display,
    )

    show_countries = await _should_show_countries_management(db_user)

    await callback.message.edit_text(
        settings_text,
        reply_markup=get_updated_subscription_settings_keyboard(
            db_user.language,
            show_countries,
            tariff=tariff,
            subscription=subscription,
            is_legacy_subscription=_legacy_subscription(subscription),
        ),
        parse_mode='HTML',
    )
    await callback.answer()


async def clear_saved_cart(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    # Очищаем как FSM, так и Redis.
    # NOTE: Intentionally deletes ALL carts (global + per-subscription cascade)
    # because this is an explicit user action ("clear my cart").  In multi-tariff
    # mode the user expects a full reset, not per-subscription cleanup.
    await state.clear()
    await user_cart_service.delete_user_cart(db_user.id)

    from app.handlers.menu import show_main_menu

    await show_main_menu(callback, db_user, db)

    await callback.answer('🗑️ Корзина очищена')


# ============== ХЕНДЛЕР ПАУЗЫ СУТОЧНОЙ ПОДПИСКИ ==============


async def handle_toggle_daily_subscription_pause(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Переключает паузу суточной подписки."""
    from app.database.crud.subscription import toggle_daily_subscription_pause
    from app.database.crud.tariff import get_tariff_by_id

    texts = get_texts(db_user.language)

    if settings.is_multi_tariff_enabled():
        await callback.answer(
            texts.t(
                'DAILY_PAUSE_MULTI_TARIFF_REDIRECT',
                'Управление суточными подписками доступно через "Мои подписки"',
            ),
            show_alert=True,
        )
        return

    subscription = db_user.subscription

    if not subscription:
        await callback.answer(texts.t('NO_SUBSCRIPTION_ERROR', '❌ У вас нет активной подписки'), show_alert=True)
        return

    # Проверяем что это суточный тариф
    tariff = None
    if subscription.tariff_id:
        tariff = await get_tariff_by_id(db, subscription.tariff_id)

    if not tariff or not getattr(tariff, 'is_daily', False):
        await callback.answer(
            texts.t('NOT_DAILY_TARIFF_ERROR', '❌ Эта функция доступна только для суточных тарифов'), show_alert=True
        )
        return

    # Прикрепляем тариф к подписке для CRUD функций
    subscription.tariff = tariff

    # Определяем, нужно ли возобновление: пауза пользователя ИЛИ остановка системой (disabled/expired)
    from app.database.models import SubscriptionStatus

    was_paused = getattr(subscription, 'is_daily_paused', False)
    is_inactive = subscription.status in (
        SubscriptionStatus.DISABLED.value,
        SubscriptionStatus.EXPIRED.value,
        SubscriptionStatus.LIMITED.value,
    )
    needs_resume = was_paused or is_inactive

    # При возобновлении проверяем баланс
    if needs_resume:
        raw_daily_price = getattr(tariff, 'daily_price_kopeks', 0)
        from app.database.crud.user import lock_user_for_pricing
        from app.services.pricing_engine import PricingEngine

        db_user = await lock_user_for_pricing(db, db_user.id)
        promo_group = PricingEngine.resolve_promo_group(db_user)
        daily_group_pct = promo_group.get_discount_percent('period', 1) if promo_group else 0
        daily_price = (
            PricingEngine.apply_discount(raw_daily_price, daily_group_pct) if daily_group_pct > 0 else raw_daily_price
        )
        if daily_price > 0 and db_user.balance_kopeks < daily_price:
            await callback.answer(
                texts.t(
                    'INSUFFICIENT_BALANCE_FOR_RESUME',
                    f'❌ Недостаточно средств для возобновления. Требуется: {settings.format_price(daily_price)}',
                ),
                show_alert=True,
            )
            return

    if needs_resume:
        resume_transaction = None
        # Списываем суточную оплату ДО активации (чтобы не было бесплатного дня)
        if daily_price > 0 and is_inactive:
            from app.database.crud.user import subtract_user_balance

            deducted = await subtract_user_balance(
                db,
                db_user,
                daily_price,
                f'Суточная оплата тарифа «{tariff.name}» (возобновление)',
                mark_as_paid_subscription=True,
            )
            if not deducted:
                await callback.answer(
                    texts.t(
                        'INSUFFICIENT_BALANCE_FOR_RESUME',
                        f'❌ Недостаточно средств для возобновления. Требуется: {settings.format_price(daily_price)}',
                    ),
                    show_alert=True,
                )
                return

            from app.database.crud.transaction import create_transaction
            from app.database.models import TransactionType

            try:
                resume_transaction = await create_transaction(
                    db=db,
                    user_id=db_user.id,
                    type=TransactionType.SUBSCRIPTION_PAYMENT,
                    amount_kopeks=daily_price,
                    description=f'Суточная оплата тарифа «{tariff.name}» (возобновление)',
                )
            except Exception as tx_error:
                logger.warning('Не удалось создать транзакцию при возобновлении', error=tx_error)

        # Принудительный resume: снимаем паузу + восстанавливаем статус ACTIVE
        from app.database.crud.subscription import resume_daily_subscription

        was_limited = subscription.status == SubscriptionStatus.LIMITED.value
        subscription = await resume_daily_subscription(db, subscription)
        message = texts.t('DAILY_SUBSCRIPTION_RESUMED', '▶️ Подписка возобновлена!')
        # Восстанавливаем connected_squads из тарифа, если очищены деактивацией
        try:
            if not subscription.connected_squads:
                squads = tariff.allowed_squads or []
                if not squads:
                    from app.database.crud.server_squad import get_all_server_squads

                    all_servers, _ = await get_all_server_squads(db, available_only=True, limit=10000)
                    squads = [s.squad_uuid for s in all_servers if s.squad_uuid]
                if squads:
                    subscription.connected_squads = squads
                    await db.commit()
                    await db.refresh(subscription)
        except Exception as sq_err:
            logger.warning('Не удалось восстановить connected_squads', error=sq_err)

        # Синхронизируем с Remnawave - активируем пользователя
        try:
            from app.services.subscription_service import SubscriptionService
            from app.services.traffic_reset_policy import lift_panel_traffic_limit, should_reset_traffic_on_daily_charge

            # Возобновление после остановки системой списывает суточную оплату —
            # обнуление счётчика решает та же политика, что и в ночном списании,
            # а не жёсткая константа. Снятие своей паузы оплатой не является.
            reset_traffic = is_inactive and should_reset_traffic_on_daily_charge(tariff)
            reset_reason = 'суточное списание (возобновление)' if reset_traffic else None

            subscription_service = SubscriptionService()
            # В multi-tariff панельная идентичность живёт на подписке, а
            # User.remnawave_id не заполняется вовсе. Гейт только по User здесь
            # означал бы новый панельный дубль на каждом возобновлении.
            _panel_user_id = (
                subscription.remnawave_id
                if settings.is_multi_tariff_enabled() and subscription.remnawave_id
                else getattr(db_user, 'remnawave_id', None)
            )
            if _panel_user_id:
                await subscription_service.update_remnawave_user(
                    db,
                    subscription,
                    reset_traffic=reset_traffic,
                    reset_reason=reset_reason,
                    sync_squads=True,
                )
            else:
                await subscription_service.create_remnawave_user(
                    db,
                    subscription,
                    reset_traffic=reset_traffic,
                    reset_reason=reset_reason,
                )
                # POST может игнорировать activeInternalSquads — отправляем PATCH
                await db.refresh(db_user)
                _panel_user_id = (
                    subscription.remnawave_id
                    if settings.is_multi_tariff_enabled() and subscription.remnawave_id
                    else getattr(db_user, 'remnawave_id', None)
                )
                if _panel_user_id and subscription.connected_squads:
                    try:
                        # Досыл сквадов — часть того же события оплаты:
                        # счётчик уже обнулён вызовом выше, второй раз не надо.
                        await subscription_service.update_remnawave_user(
                            db,
                            subscription,
                            reset_traffic=False,
                            sync_squads=True,
                        )
                    except Exception as patch_err:
                        logger.warning('Не удалось синхронизировать сквады после создания', error=patch_err)

            if reset_traffic:
                # Счётчик бота ведут по данным панели, но до ближайшего прохода
                # мониторинга он показывал бы исчерпанный трафик.
                subscription.traffic_used_gb = 0.0
                await db.commit()
                if was_limited:
                    # PATCH сам по себе статус «трафик исчерпан» не снимает.
                    await lift_panel_traffic_limit(db, subscription, service=subscription_service)
            logger.info(
                '✅ Синхронизировано с Remnawave после возобновления суточной подписки', subscription_id=subscription.id
            )
        except Exception as e:
            logger.error('Ошибка синхронизации с Remnawave при возобновлении', error=e)
            from app.services.remnawave_retry_queue import remnawave_retry_queue

            remnawave_retry_queue.enqueue(
                subscription_id=subscription.id,
                user_id=db_user.id,
                action='update',
            )

        # Отправляем уведомление администраторам о возобновлении суточной подписки
        if resume_transaction is not None:
            try:
                from app.services.admin_notification_service import AdminNotificationService

                if settings.ADMIN_NOTIFICATIONS_ENABLED and settings.BOT_TOKEN:
                    notification_service = AdminNotificationService(callback.bot)
                    await notification_service.send_subscription_purchase_notification(
                        db=db,
                        user=db_user,
                        subscription=subscription,
                        transaction=resume_transaction,
                        period_days=1,
                        was_trial_conversion=False,
                        amount_kopeks=daily_price,
                        purchase_type='renewal',
                    )
            except Exception as notif_err:
                logger.error('Не удалось отправить уведомление администраторам при возобновлении', error=notif_err)
    else:
        # Подписка активна, ставим на паузу
        subscription = await toggle_daily_subscription_pause(db, subscription)
        message = texts.t('DAILY_SUBSCRIPTION_PAUSED', '⏸️ Подписка приостановлена!')

    await callback.answer(message, show_alert=True)

    # Возвращаемся в меню подписки - вызываем show_subscription_info
    await db.refresh(db_user)
    await show_subscription_info(callback, db_user, db)


# ============== ХЕНДЛЕРЫ ПЛАТНОГО ТРИАЛА ==============


def register_handlers(dp: Dispatcher):
    update_traffic_prices()

    dp.callback_query.register(show_subscription_info, F.data == 'menu_subscription')

    # Multi-tariff: "My subscriptions" list and detail views
    from app.handlers.subscription.my_subscriptions import show_my_subscriptions, show_subscription_detail

    dp.callback_query.register(show_my_subscriptions, F.data == 'my_subscriptions')
    dp.callback_query.register(show_subscription_detail, F.data.startswith('sm:'))

    # Multi-tariff delegation handlers from subscription detail view
    from app.handlers.subscription.my_subscriptions import (
        handle_change_devices_menu,
        handle_device_management_menu,
        handle_subscription_devices,
        handle_subscription_extend,
        handle_subscription_link,
        handle_subscription_traffic,
    )

    dp.callback_query.register(handle_subscription_link, F.data.startswith('sl:'))
    dp.callback_query.register(handle_subscription_extend, F.data.startswith('se:'))
    dp.callback_query.register(handle_subscription_traffic, F.data.startswith('st:'))
    dp.callback_query.register(handle_subscription_devices, F.data.startswith('sd:'))
    dp.callback_query.register(handle_change_devices_menu, F.data.startswith('change_devices_menu:'))
    dp.callback_query.register(handle_device_management_menu, F.data.startswith('device_management:'))

    # Subscription revoke (reissue)
    from app.handlers.subscription.revoke import (
        confirm_subscription_revoke,
        start_multi_revoke,
        start_subscription_revoke,
    )

    dp.callback_query.register(start_subscription_revoke, F.data == 'subscription_revoke')
    dp.callback_query.register(confirm_subscription_revoke, F.data == 'subscription_revoke_confirm')
    dp.callback_query.register(start_multi_revoke, F.data.startswith('sr:'))

    dp.callback_query.register(show_trial_offer, F.data == 'menu_trial')

    dp.callback_query.register(activate_trial, F.data == 'trial_activate')
    dp.callback_query.register(
        start_subscription_purchase, F.data.in_(['menu_buy', 'subscription_upgrade', 'subscription_purchase'])
    )

    # Хендлеры платного триала

    dp.callback_query.register(handle_add_countries, F.data == 'subscription_add_countries')

    dp.callback_query.register(handle_switch_traffic, F.data == 'subscription_switch_traffic')

    dp.callback_query.register(confirm_switch_traffic, F.data.startswith('switch_traffic_'))

    dp.callback_query.register(execute_switch_traffic, F.data.startswith('confirm_switch_traffic_'))

    dp.callback_query.register(handle_change_devices, F.data == 'subscription_change_devices')

    dp.callback_query.register(confirm_change_devices, F.data.startswith('change_devices_'))

    dp.callback_query.register(execute_change_devices, F.data.startswith('confirm_change_devices_'))

    dp.callback_query.register(handle_extend_subscription, F.data == 'subscription_extend')

    dp.callback_query.register(handle_reset_traffic, F.data == 'subscription_reset_traffic')

    dp.callback_query.register(confirm_add_devices, F.data.startswith('add_devices_'))

    dp.callback_query.register(confirm_extend_subscription, F.data.startswith('extend_period_'))

    dp.callback_query.register(confirm_reset_traffic, F.data == 'confirm_reset_traffic')

    dp.callback_query.register(handle_reset_devices, F.data == 'subscription_reset_devices')

    dp.callback_query.register(confirm_reset_devices, F.data == 'confirm_reset_devices')

    dp.callback_query.register(
        return_to_saved_cart,
        F.data == 'return_to_saved_cart',
    )

    dp.callback_query.register(
        clear_saved_cart,
        F.data == 'clear_saved_cart',
    )

    dp.callback_query.register(handle_autopay_menu, F.data == 'subscription_autopay')

    dp.callback_query.register(toggle_autopay, F.data.in_(['autopay_enable', 'autopay_disable']))

    dp.callback_query.register(show_autopay_days, F.data == 'autopay_set_days')

    dp.callback_query.register(show_autopay_period, F.data == 'autopay_set_period')

    dp.callback_query.register(handle_sbp_recurring_menu, F.data == 'sbp_recurring_menu')

    dp.callback_query.register(handle_sbp_recurring_enable, F.data == 'sbp_recurring_enable')

    dp.callback_query.register(handle_sbp_recurring_enable_for, F.data.startswith('sbp_recurring_enable_for:'))

    dp.callback_query.register(handle_sbp_recurring_cancel, F.data == 'sbp_recurring_cancel')

    dp.callback_query.register(handle_sbp_recurring_cancel_confirm, F.data == 'sbp_recurring_cancel_confirm')
    dp.callback_query.register(handle_subscription_cancel, F.data == 'subscription_cancel')
    dp.callback_query.register(set_autopay_days, F.data.startswith('autopay_days_'))
    dp.callback_query.register(set_autopay_period, F.data.startswith('autopay_period_'))
    dp.callback_query.register(handle_manage_country, F.data.startswith('country_manage_'))
    dp.callback_query.register(apply_countries_changes, F.data == 'countries_apply')
    dp.callback_query.register(claim_discount_offer, F.data.startswith('claim_discount_'))
    dp.callback_query.register(
        handle_promo_offer_close,
        F.data == 'promo_offer_close',
    )
    dp.callback_query.register(handle_happ_download_request, F.data == 'subscription_happ_download')
    dp.callback_query.register(
        handle_happ_download_platform_choice,
        F.data.in_(
            [
                'happ_download_ios',
                'happ_download_android',
                'happ_download_pc',
                'happ_download_macos',
                'happ_download_windows',
            ]
        ),
    )

    dp.callback_query.register(handle_happ_download_close, F.data == 'happ_download_close')

    dp.callback_query.register(handle_happ_download_back, F.data == 'happ_download_back')

    dp.callback_query.register(handle_connect_subscription, F.data.startswith('subscription_connect'))

    dp.callback_query.register(handle_device_guide, F.data.startswith('device_guide_'))

    dp.callback_query.register(handle_app_selection, F.data.startswith('app_list_'))

    dp.callback_query.register(handle_specific_app_guide, F.data.startswith('app_') & ~F.data.startswith('app_list_'))

    dp.callback_query.register(handle_open_subscription_link, F.data.startswith('open_subscription_link'))

    dp.callback_query.register(handle_subscription_settings, F.data == 'subscription_settings')

    dp.callback_query.register(handle_toggle_daily_subscription_pause, F.data == 'toggle_daily_subscription_pause')

    dp.callback_query.register(handle_no_traffic_packages, F.data == 'no_traffic_packages')

    dp.callback_query.register(handle_device_management, F.data == 'subscription_manage_devices')

    dp.callback_query.register(handle_devices_page, F.data.startswith('devices_page_'))

    dp.callback_query.register(handle_single_device_reset, F.data.regexp(r'^reset_device_\d+_\d+$'))

    # Локальное переименование устройства (alias). Callback пускает FSM-prompt,
    # текстовый handler ловит ответ юзера (см. process_device_rename ниже).
    # NB: `SubscriptionStates` уже импортирован на уровне модуля (строка 107) —
    # повторный локальный `from app.states import …` превратил бы имя в local
    # и сломал бы строку 4197 с UnboundLocalError на старте.
    from app.handlers.subscription.devices import (
        cancel_device_rename,
        process_device_rename,
        start_device_rename,
    )

    dp.callback_query.register(start_device_rename, F.data.regexp(r'^device_rename_\d+_\d+$'))
    # Кнопка «Отмена» в промпте переименования — чистит FSM и возвращает список.
    dp.callback_query.register(cancel_device_rename, F.data == 'device_rename_cancel')
    # F.text — игнорируем стикеры/фото/voice пока юзер в FSM, иначе
    # message.text==None трактуется как пустая строка и очищает alias.
    dp.message.register(process_device_rename, SubscriptionStates.renaming_device, F.text)

    dp.callback_query.register(handle_all_devices_reset_from_management, F.data == 'reset_all_devices')

    dp.callback_query.register(show_device_connection_help, F.data == 'device_connection_help')

    # Регистрируем обработчики покупки по тарифам
    from .tariff_purchase import register_tariff_purchase_handlers

    register_tariff_purchase_handlers(dp)

    # Регистрируем обработчик для простой покупки
    dp.callback_query.register(handle_simple_subscription_purchase, F.data == 'simple_subscription_purchase')


async def handle_simple_subscription_purchase(
    callback: types.CallbackQuery,
    state: FSMContext,
    db_user: User,
    db: AsyncSession,
):
    """Обрабатывает простую покупку подписки."""
    get_texts(db_user.language)

    if not settings.SIMPLE_SUBSCRIPTION_ENABLED:
        await callback.answer('❌ Простая покупка подписки временно недоступна', show_alert=True)
        return

    # This callback carries no subscription id. Never choose an arbitrary
    # primary subscription for a multi-subscription account.
    if settings.is_multi_tariff_enabled():
        await callback.answer('Выберите подписку через «Мои подписки»', show_alert=True)
        return

    if db_user.restriction_subscription:
        await callback.answer('Покупка подписки ограничена администратором', show_alert=True)
        return

    # Определяем ограничение по устройствам для текущего режима
    resolve_simple_subscription_device_limit()

    # Проверяем, есть ли у пользователя активная подписка
    from app.database.crud.subscription import get_subscription_by_user_id

    current_subscription = await get_subscription_by_user_id(db, db_user.id)

    if current_subscription and current_subscription.tariff_id:
        await _extend_simple_tariff_subscription(callback, db_user, db, current_subscription)
        return

    from .tariff_purchase import show_tariffs_list

    await show_tariffs_list(callback, db_user, db, state)
    return

    # Если у пользователя уже есть активная подписка, продлеваем её


async def _extend_simple_tariff_subscription(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    subscription: Subscription,
):
    """Renew the attached tariff without applying classic purchase defaults."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database.crud.user import lock_user_for_pricing
    from app.services.subscription_renewal_service import SubscriptionRenewalChargeError, SubscriptionRenewalService

    subscription_id = subscription.id
    db_user = await lock_user_for_pricing(db, db_user.id)
    subscription = await db.scalar(
        select(Subscription)
        .where(Subscription.id == subscription_id, Subscription.user_id == db_user.id)
        .options(selectinload(Subscription.tariff))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    tariff = subscription.tariff if subscription else None
    period_days = settings.SIMPLE_SUBSCRIPTION_PERIOD_DAYS
    # Missing periods are not zero-priced periods. Trial conversion and daily
    # billing use their own existing flows instead of classic defaults.
    if (
        not tariff
        or not tariff.is_active
        or tariff.is_daily
        or subscription.is_trial
        or subscription.status in (SubscriptionStatus.DISABLED.value, SubscriptionStatus.PENDING.value)
        or db_user.restriction_subscription
        or period_days <= 0
        or (tariff.period_prices or {}).get(str(period_days)) is None
    ):
        await db.rollback()
        await callback.answer('Откройте продление подписки и выберите доступный тариф и период', show_alert=True)
        return

    pricing = await pricing_engine.calculate_renewal_price(db, subscription, period_days, user=db_user)
    texts = get_texts(db_user.language)
    price = pricing.final_total
    if price > db_user.balance_kopeks:
        missing = price - db_user.balance_kopeks
        user_id = db_user.id
        language = db_user.language
        balance = db_user.balance_kopeks
        cart = {
            'cart_mode': 'extend',
            'subscription_id': subscription.id,
            'tariff_id': tariff.id,
            'period_days': period_days,
            'total_price': price,
            'user_id': user_id,
            'saved_cart': True,
            'missing_amount': missing,
            'return_to_cart': True,
            'device_limit': subscription.device_limit,
            'devices': subscription.device_limit,
            'traffic_limit_gb': subscription.traffic_limit_gb,
            'traffic_gb': subscription.traffic_limit_gb,
            'countries': list(subscription.connected_squads or []),
            'consume_promo_offer': pricing.promo_offer_discount > 0,
        }
        # Do not hold financial locks while contacting Redis or Telegram.
        await db.rollback()
        await user_cart_service.save_user_cart(user_id, cart)
        message = texts.t(
            'ADDON_INSUFFICIENT_FUNDS_MESSAGE',
            '⚠️ <b>Недостаточно средств</b>\n\nСтоимость услуги: {required}\n'
            'На балансе: {balance}\nНе хватает: {missing}\n\nВыберите способ пополнения.',
        ).format(
            required=texts.format_price(price), balance=texts.format_price(balance), missing=texts.format_price(missing)
        )
        await callback.message.edit_text(
            message,
            reply_markup=get_insufficient_balance_keyboard(language, amount_kopeks=missing, has_saved_cart=True),
            parse_mode='HTML',
        )
        await callback.answer()
        return

    try:
        result = await SubscriptionRenewalService().finalize(
            db, db_user, subscription, pricing, payment_method=PaymentMethod.BALANCE
        )
    except SubscriptionRenewalChargeError:
        await callback.answer('⚠ Ошибка списания средств', show_alert=True)
        return
    await callback.message.edit_text(
        '✅ Подписка успешно продлена!\n\n'
        f'⏰ Добавлено: {period_days} дней\n'
        f'Действует до: {format_local_datetime(result.subscription.end_date, "%d.%m.%Y %H:%M")}\n\n'
        f'💰 Списано: {texts.format_price(price)}',
        reply_markup=get_back_keyboard(db_user.language),
    )
    await callback.answer()
