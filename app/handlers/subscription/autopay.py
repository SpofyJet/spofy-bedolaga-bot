import html
from typing import Any

import structlog
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.subscription import update_subscription_autopay
from app.database.models import User
from app.keyboards.inline import (
    get_autopay_days_keyboard,
    get_autopay_keyboard,
    get_autopay_period_keyboard,
)
from app.localization.texts import get_texts
from app.services.user_cart_service import user_cart_service
from app.utils.formatters import format_datetime
from app.utils.photo_message import edit_or_answer_photo


logger = structlog.get_logger(__name__)


async def _resolve_subscription(callback, db_user, db, state=None):
    """Resolve subscription — delegates to shared resolve_subscription_from_context."""
    from .common import resolve_subscription_from_context

    return await resolve_subscription_from_context(callback, db_user, db, state)


async def handle_autopay_menu(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    texts = get_texts(db_user.language)
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if not subscription:
        await callback.answer(
            texts.t('SUBSCRIPTION_ACTIVE_REQUIRED', '⚠️ У вас нет активной подписки!'),
            show_alert=True,
        )
        return

    # Суточные подписки имеют свой механизм продления, глобальный autopay не применяется
    try:
        await db.refresh(subscription, ['tariff'])
    except Exception as refresh_error:
        logger.warning('Не удалось подгрузить тариф подписки', subscription_id=subscription.id, error=refresh_error)
    if subscription.tariff and getattr(subscription.tariff, 'is_daily', False):
        # Баланс-автоплатёж для суточных тарифов недоступен, но СБП-автопродление
        # Platega суточный интервал поддерживает (`day`) — вход в него должен
        # оставаться достижимым, поэтому кнопку добавляем в тот же экран.
        daily_keyboard_rows: list[list[types.InlineKeyboardButton]] = []
        if settings.is_platega_recurrent_enabled():
            daily_keyboard_rows.append(
                [
                    types.InlineKeyboardButton(
                        text=texts.t('SBP_RECURRING_MENU_BUTTON', '⚡ Автопродление через СБП'),
                        callback_data='sbp_recurring_menu',
                    )
                ]
            )
        back_cb = f'sm:{sub_id}' if sub_id and settings.is_multi_tariff_enabled() else 'menu_subscription'
        daily_keyboard_rows.append([types.InlineKeyboardButton(text=texts.BACK, callback_data=back_cb)])

        await callback.message.edit_text(
            texts.t(
                'AUTOPAY_NOT_AVAILABLE_FOR_DAILY',
                'Автоплатеж недоступен для суточных тарифов. Списание происходит автоматически раз в сутки.',
            ),
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=daily_keyboard_rows),
        )
        await callback.answer()
        return

    status = (
        texts.t('AUTOPAY_STATUS_ENABLED', 'включен')
        if subscription.autopay_enabled
        else texts.t('AUTOPAY_STATUS_DISABLED', 'выключен')
    )
    days = subscription.autopay_days_before

    period_value = getattr(subscription, 'autopay_period_days', None)
    if period_value:
        period_text = texts.t('AUTOPAY_PERIOD_VALUE', '{days} дн.').format(days=period_value)
    else:
        period_text = texts.t('AUTOPAY_PERIOD_DEFAULT_VALUE', 'по умолчанию (самый дешёвый период тарифа)')

    text = texts.t(
        'AUTOPAY_MENU_TEXT',
        (
            '💳 <b>Автоплатеж</b>\n\n'
            '📊 <b>Статус:</b> {status}\n'
            '⏰ <b>Списание за:</b> {days} дн. до окончания\n'
            '📅 <b>Период продления:</b> {period}\n\n'
            'Выберите действие:'
        ),
    ).format(status=status, days=days, period=period_text)

    keyboard = get_autopay_keyboard(db_user.language, sub_id=sub_id)
    if settings.is_platega_recurrent_enabled():
        # Вставляем перед последней строкой (Back), чтобы кнопка СБП была
        # среди основных действий, а не под ней.
        keyboard.inline_keyboard.insert(
            -1,
            [
                types.InlineKeyboardButton(
                    text=texts.t('SBP_RECURRING_MENU_BUTTON', '⚡ Автопродление через СБП'),
                    callback_data='sbp_recurring_menu',
                )
            ],
        )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode='HTML',
    )
    await callback.answer()


async def toggle_autopay(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return
    enable = callback.data.startswith('autopay_enable')

    if enable:
        # Trial subscriptions cannot use autopay
        if subscription.is_trial or subscription.is_trial is None:
            texts = get_texts(db_user.language)
            await callback.answer(
                texts.t(
                    'AUTOPAY_NOT_AVAILABLE_TRIAL',
                    'Автоплатеж недоступен для пробных подписок.',
                ),
                show_alert=True,
            )
            return

        # Classic subscriptions cannot use autopay when tariff mode is enabled
        if not subscription.tariff_id:
            texts = get_texts(db_user.language)
            await callback.answer(
                texts.t(
                    'AUTOPAY_NOT_AVAILABLE_CLASSIC',
                    'Автоплатеж недоступен. Для продления необходимо выбрать тариф.',
                ),
                show_alert=True,
            )
            return

    # Суточные подписки имеют свой механизм продления (DailySubscriptionService),
    # глобальный autopay для них запрещён
    if enable:
        try:
            await db.refresh(subscription, ['tariff'])
        except Exception:
            logger.warning('Ignored error in toggle_autopay', exc_info=True)
        if subscription.tariff and getattr(subscription.tariff, 'is_daily', False):
            texts = get_texts(db_user.language)
            await callback.answer(
                texts.t(
                    'AUTOPAY_NOT_AVAILABLE_FOR_DAILY',
                    'Автоплатеж недоступен для суточных тарифов. Списание происходит автоматически раз в сутки.',
                ),
                show_alert=True,
            )
            return

    # n2: включение баланс-автоплатежа централизованно гасит провайдерские
    # привязки этой подписки (см. crud.update_subscription_autopay) —
    # предупреждаем alert'ом, флоу не прерываем.
    engines_warning = None
    if enable:
        try:
            from app.services.recurrent_amount import get_active_recurrent_engines, recurrent_engines_warning

            _engines = await get_active_recurrent_engines(db, subscription)
            _warning = recurrent_engines_warning(get_texts(db_user.language), _engines, enabling='balance')
            engines_warning = _warning or None
        except Exception:
            logger.warning('Ignored error in toggle_autopay', exc_info=True)

    await update_subscription_autopay(db, subscription, enable)

    if enable:
        # Обратное взаимоисключение: включение баланс-автоплатежа должно
        # отменить активную СБП-автоподписку Platega у той же подписки —
        # иначе оба движка продления начнут списывать параллельно (двойное
        # списание). Прямое взаимоисключение (СБП -> выключение
        # balance-autopay) уже реализовано в create_platega_sbp_subscription.
        from app.services.payment.platega import cancel_platega_recurring_for_subscription_safe

        await cancel_platega_recurring_for_subscription_safe(db, subscription.id)

    texts = get_texts(db_user.language)
    status = texts.t('AUTOPAY_STATUS_ENABLED', 'включен') if enable else texts.t('AUTOPAY_STATUS_DISABLED', 'выключен')
    if engines_warning:
        # Один callback.answer на запрос: предупреждение вытесняет тост успеха.
        await callback.answer(engines_warning, show_alert=True)
    else:
        await callback.answer(texts.t('AUTOPAY_TOGGLE_SUCCESS', '✅ Автоплатеж {status}!').format(status=status))

    try:
        await handle_autopay_menu(callback, db_user, db, state)
    except TelegramBadRequest as e:
        if 'message is not modified' in str(e):
            pass
        else:
            raise


async def show_autopay_days(callback: types.CallbackQuery, db_user: User):
    texts = get_texts(db_user.language)
    await callback.message.edit_text(
        texts.t(
            'AUTOPAY_SELECT_DAYS_PROMPT',
            '⏰ Выберите за сколько дней до окончания списывать средства:',
        ),
        reply_markup=get_autopay_days_keyboard(db_user.language),
    )
    await callback.answer()


async def set_autopay_days(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return
    base_data = callback.data.split(':')[0]
    days = int(base_data.split('_')[2])

    await update_subscription_autopay(db, subscription, subscription.autopay_enabled, days)

    texts = get_texts(db_user.language)
    await callback.answer(texts.t('AUTOPAY_DAYS_SET', '✅ Установлено {days} дней!').format(days=days))

    await handle_autopay_menu(callback, db_user, db, state)


def _get_subscription_renewal_periods(subscription) -> list[int]:
    """Available renewal periods for a subscription: tariff periods (preferred) or global env list."""
    tariff = getattr(subscription, 'tariff', None)
    if tariff:
        periods = tariff.get_available_periods() or []
        if periods:
            return sorted(periods)
    return sorted(settings.get_available_renewal_periods())


async def show_autopay_period(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    """Period picker UI for autopay."""
    texts = get_texts(db_user.language)
    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return

    try:
        await db.refresh(subscription, ['tariff'])
    except Exception as refresh_error:
        logger.warning('Не удалось подгрузить тариф подписки', subscription_id=subscription.id, error=refresh_error)

    periods = _get_subscription_renewal_periods(subscription)
    current = getattr(subscription, 'autopay_period_days', None)

    await callback.message.edit_text(
        texts.t(
            'AUTOPAY_SELECT_PERIOD_PROMPT',
            '📅 Выберите период, на который автоплатёж будет продлевать подписку:',
        ),
        reply_markup=get_autopay_period_keyboard(periods, current, db_user.language),
    )
    await callback.answer()


async def set_autopay_period(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None):
    """Handle period selection (autopay_period_<N> or autopay_period_default)."""
    from app.database.crud.subscription import update_subscription_autopay as _update_autopay

    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if subscription is None:
        return

    raw = callback.data.split(':')[0]
    suffix = raw[len('autopay_period_') :] if raw.startswith('autopay_period_') else ''
    texts = get_texts(db_user.language)

    if suffix == 'default':
        await _update_autopay(db, subscription, subscription.autopay_enabled, period_days=None)
        await callback.answer(texts.t('AUTOPAY_PERIOD_SET_DEFAULT', '✅ Используется период по умолчанию.'))
    else:
        try:
            days = int(suffix)
        except ValueError:
            await callback.answer(texts.t('INVALID_REQUEST', 'Invalid request'), show_alert=True)
            return

        try:
            await db.refresh(subscription, ['tariff'])
        except Exception:
            logger.warning('Ignored error in set_autopay_period', exc_info=True)

        available = _get_subscription_renewal_periods(subscription)
        if days not in available:
            await callback.answer(
                texts.t(
                    'AUTOPAY_PERIOD_NOT_AVAILABLE',
                    '❌ Этот период недоступен для данной подписки.',
                ),
                show_alert=True,
            )
            return

        await _update_autopay(db, subscription, subscription.autopay_enabled, period_days=days)
        await callback.answer(texts.t('AUTOPAY_PERIOD_SET', '✅ Период автоплатежа: {days} дн.').format(days=days))

    await handle_autopay_menu(callback, db_user, db, state)


def _platega_sbp_status_text(record: Any, texts) -> str:
    """Pure builder: человекочитаемая строка статуса СБП-автопродления Platega.

    ``record`` — ``PlategaSubscription``-подобный объект (реальная модель или
    ``SimpleNamespace`` в тестах) с атрибутами ``status``/``next_charge_at``,
    либо ``None`` (автопродление не подключено). Не трогает БД/сеть — чистая
    функция для unit-тестов и переиспользования в других UI (бот/кабинет).
    """
    if record is None:
        return texts.t('SBP_RECURRING_STATUS_NONE', 'не подключено')

    status = getattr(record, 'status', None)

    if status == 'PENDING':
        return texts.t('SBP_RECURRING_STATUS_PENDING', 'ожидает подтверждения в банке')

    if status == 'ACTIVE':
        next_charge_at = getattr(record, 'next_charge_at', None)
        when = (
            format_datetime(next_charge_at)
            if next_charge_at
            else texts.t('SBP_RECURRING_NEXT_CHARGE_UNKNOWN', 'уточняется')
        )
        return texts.t(
            'SBP_RECURRING_STATUS_ACTIVE',
            'активно (следующее списание {next_charge_at})',
        ).format(next_charge_at=when)

    if status == 'PAST_DUE':
        return texts.t('SBP_RECURRING_STATUS_PAST_DUE', 'просрочено')

    if status == 'CANCELLED':
        return texts.t('SBP_RECURRING_STATUS_CANCELLED', 'отменено')

    if status == 'FAILED':
        return texts.t('SBP_RECURRING_STATUS_FAILED', 'не удалось подключить')

    return texts.t('SBP_RECURRING_STATUS_UNKNOWN', 'статус неизвестен ({status})').format(status=status)


async def handle_sbp_recurring_menu(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None
):
    """СБП-автопродление Platega: статус текущей подписки + Enable/Cancel."""
    texts = get_texts(db_user.language)

    if not settings.is_platega_recurrent_enabled():
        await callback.answer(
            texts.t('SBP_RECURRING_UNAVAILABLE', '⚠️ Автопродление через СБП сейчас недоступно'),
            show_alert=True,
        )
        return

    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if not subscription:
        await callback.answer(
            texts.t('SUBSCRIPTION_ACTIVE_REQUIRED', '⚠️ У вас нет активной подписки!'),
            show_alert=True,
        )
        return

    from app.database.crud.platega_subscription import get_active_platega_subscription_by_subscription

    record = await get_active_platega_subscription_by_subscription(db, subscription.id)
    status_text = _platega_sbp_status_text(record, texts)

    text = texts.t(
        'SBP_RECURRING_MENU_TEXT',
        '⚡ <b>Автопродление через СБП</b>\n\n📊 <b>Статус:</b> {status}',
    ).format(status=status_text)

    if record is None:
        # Не предлагаем «Подключить», если каденс тарифа невыразим в Platega
        # (например «вечный» тариф на 2222 дня) или у тарифа нет цены за него:
        # клик по «Подключить» всё равно завершался бы ошибкой — честнее сразу
        # показать недоступность и оставить только «Назад».
        try:
            await db.refresh(subscription, ['tariff'])
        except Exception:
            # refresh может упасть на detached/уже загруженном объекте — тогда
            # читаем то, что есть (паритет с enable-хендлером).
            logger.warning('Ignored error in handle_sbp_recurring_menu', exc_info=True)
        _menu_tariff = getattr(subscription, 'tariff', None)
        try:
            from app.services.autopay_period import resolve_autopay_period_candidate
            from app.services.platega_recurrent import resolve_platega_cadence

            _menu_period = (
                resolve_autopay_period_candidate(getattr(subscription, 'autopay_period_days', None), _menu_tariff)
                or resolve_autopay_period_candidate(settings.DEFAULT_AUTOPAY_PERIOD_DAYS, _menu_tariff)
                or (_menu_tariff.get_shortest_period() if _menu_tariff else None)
                or 30
            )
            _menu_cadence = resolve_platega_cadence(_menu_period, bool(getattr(_menu_tariff, 'is_daily', False)))
            _menu_available = (
                _menu_tariff is not None
                and _menu_cadence is not None
                and bool(_menu_tariff.get_purchasable_price_for_period(_menu_cadence[2]))
            )
        except Exception:
            # Проверка не должна ломать меню: при любой ошибке оставляем
            # кнопку — enable-хендлер покажет осмысленную причину (ValueError).
            _menu_available = True
        if not _menu_available:
            text += '\n\n' + texts.t(
                'SBP_RECURRING_MENU_UNAVAILABLE',
                '⚠️ Для вашего тарифа автопродление через СБП недоступно.',
            )
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_autopay')],
                ]
            )
            # n7: точка входа может быть медиа-рассылкой — edit_text по фото
            # падает; edit_or_answer_photo сам выберет caption/текст.
            await edit_or_answer_photo(callback, text, keyboard)
            await callback.answer()
            return

    if record is not None:
        # get_active_platega_subscription_by_subscription уже фильтрует по
        # PENDING/ACTIVE/PAST_DUE — любая непустая запись «активна» для целей UI.
        action_button = types.InlineKeyboardButton(
            text=texts.t('SBP_RECURRING_CANCEL_BUTTON', '❌ Отменить автооплату'),
            callback_data='sbp_recurring_cancel',
        )
        action_rows = [[action_button]]
        # Брошенная привязка (PENDING): возвращаем ссылку на банковскую
        # форму — завершить привязку можно той же ссылкой (enable
        # идемпотентен, redirect_url хранится в записи). Без этой кнопки
        # юзер, потерявший сообщение со ссылкой, попадал в тупик с одной
        # «Отменить».
        _pending_url = getattr(record, 'redirect_url', None)
        if record.status == 'PENDING' and _pending_url:
            action_rows.insert(
                0,
                [
                    types.InlineKeyboardButton(
                        text=texts.t('SBP_RECURRING_CONFIRM_BANK_BUTTON', '🏦 Подтвердить в банке'),
                        url=_pending_url,
                    )
                ],
            )
    else:
        action_button = types.InlineKeyboardButton(
            text=texts.t('SBP_RECURRING_ENABLE_BUTTON', '✅ Подключить'),
            callback_data='sbp_recurring_enable',
            style='success',
        )
        action_rows = [[action_button]]

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            *action_rows,
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='subscription_autopay')],
        ]
    )

    # n7: точка входа может быть медиа-рассылкой — безопасная замена.
    await edit_or_answer_photo(callback, text, keyboard)
    await callback.answer()


class _OneShotCallbackReply:
    """Ответ на нажатие ровно один раз; следующие сообщения — обычным сообщением.

    Telegram принимает один answer() на нажатие: если до ошибки уже показали
    предупреждение, второй ответ отвергается, и человек видел только предупреждение.
    """

    def __init__(self, callback: types.CallbackQuery):
        self.callback = callback
        self.answered = False

    async def alert(self, text: str, *, show_alert: bool = True, escape: bool = False) -> None:
        if not self.answered:
            self.answered = True
            await self.callback.answer(text, show_alert=show_alert)
            return
        if isinstance(self.callback.message, types.Message):
            await self.callback.message.answer(html.escape(text) if escape else text)

    async def done(self) -> None:
        if not self.answered:
            self.answered = True
            await self.callback.answer()


async def handle_sbp_recurring_enable(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None
):
    """Подключить СБП-автопродление: создать рекуррентную Platega-подписку и
    показать кнопку подтверждения в банке."""
    texts = get_texts(db_user.language)

    if not settings.is_platega_recurrent_enabled():
        await callback.answer(
            texts.t('SBP_RECURRING_UNAVAILABLE', '⚠️ Автопродление через СБП сейчас недоступно'),
            show_alert=True,
        )
        return

    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if not subscription:
        await callback.answer(
            texts.t('SUBSCRIPTION_ACTIVE_REQUIRED', '⚠️ У вас нет активной подписки!'),
            show_alert=True,
        )
        return

    # Trial subscriptions cannot authorize a real recurring bank payment
    # (same guard as toggle_autopay's balance-autopay enable path).
    if subscription.is_trial or subscription.is_trial is None:
        await callback.answer(
            texts.t(
                'AUTOPAY_NOT_AVAILABLE_TRIAL',
                'Автоплатеж недоступен для пробных подписок.',
            ),
            show_alert=True,
        )
        return

    # tariff обязателен: create_platega_sbp_subscription вызывает
    # tariff.get_purchasable_price_for_period(...) без None-guard'а (контракт
    # Task 5 — тариф считается обязательным для СБП-автопродления).
    try:
        await db.refresh(subscription, ['tariff'])
    except Exception:
        # refresh может упасть на detached/уже загруженном объекте — тогда
        # просто читаем то, что есть: None-guard ниже отработает.
        logger.warning('Ignored error in handle_sbp_recurring_enable', exc_info=True)

    tariff = getattr(subscription, 'tariff', None)
    if tariff is None:
        await callback.answer(
            texts.t(
                'SBP_RECURRING_NO_TARIFF',
                '⚠️ Автопродление через СБП доступно только для подписок с тарифом.',
            ),
            show_alert=True,
        )
        return

    reply = _OneShotCallbackReply(callback)

    # n2: предупреждение о смене движка:
    # баланс-автоплатёж этой подписки будут отключены при создании
    # СБП-привязки — предупреждаем alert'ом, флоу не прерываем.
    try:
        from app.services.recurrent_amount import get_active_recurrent_engines, recurrent_engines_warning

        _engines = await get_active_recurrent_engines(db, subscription)
        _warning = recurrent_engines_warning(texts, _engines, enabling='platega')
        if _warning:
            await reply.alert(_warning)
    except Exception:
        logger.warning('Ignored error in handle_sbp_recurring_enable', exc_info=True)

    from app.services.payment.platega import enable_platega_sbp_recurring

    # Если предупреждение о смене способа уже ответило на нажатие, ошибки ниже
    # уходят сообщением (reply.alert) — иначе их не было бы видно.
    try:
        result = await enable_platega_sbp_recurring(db, user_id=db_user.id, subscription=subscription, tariff=tariff)
    except ValueError as error:
        # ValueError — осмысленная причина (период/цена/состояние подписки),
        # показываем её пользователю как есть вместо общей «попробуйте позже».
        await reply.alert(str(error), escape=True)
        return
    except RuntimeError as error:
        logger.warning(
            'Не удалось подключить СБП-автопродление',
            error=str(error),
            subscription_id=subscription.id,
        )
        await reply.alert(
            texts.t(
                'SBP_RECURRING_ENABLE_ERROR',
                '❌ Не удалось подключить автопродление через СБП. Попробуйте позже.',
            )
        )
        return

    redirect_url = result.get('redirect_url')
    if not redirect_url:
        # Идемпотентный возврат уже существующей подписки без сохранённой
        # ссылки — показываем статус вместо кнопки с пустым url (Telegram
        # такую кнопку не примет).
        await reply.alert(
            texts.t('SBP_RECURRING_ALREADY_ACTIVE', 'СБП-автопродление уже подключено.'), show_alert=False
        )
        await handle_sbp_recurring_menu(callback, db_user, db, state)
        return

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('SBP_RECURRING_CONFIRM_BUTTON', '🏦 Подтвердить в банке'),
                    url=redirect_url,
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='sbp_recurring_menu')],
        ]
    )

    # n7: точка входа может быть медиа-рассылкой (кнопка из broadcast'а) —
    # edit_text по фото упадёт; edit_or_answer_photo сам выберет caption/текст.
    await edit_or_answer_photo(
        callback,
        texts.t(
            'SBP_RECURRING_ENABLE_SUCCESS',
            '⚡ <b>Автопродление через СБП</b>\n\n'
            'Подтвердите подключение в банковском приложении по кнопке ниже.\n'
            'После подтверждения автопродление станет активным.',
        )
        # Сумма и шаг списания — ДО формы банка: юзер видит «270 ₽ каждые
        # 30 дн.» в боте, а не только на форме Platega (первое списание
        # происходит сразу при подтверждении привязки — честно предупреждаем).
        + texts.t(
            'SBP_RECURRING_PRICE_LINE',
            '\n\n💰 <b>{amount}</b> каждые {days} дн. — первое списание сразу при подтверждении.',
        ).format(
            amount=f'{(result.get("amount_kopeks") or 0) // 100} ₽',
            days=result.get('charge_days') or 30,
        ),
        keyboard,
    )
    await reply.done()


async def handle_sbp_recurring_enable_for(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None
):
    """Включить СБП-автопродление для КОНКРЕТНОЙ подписки (оффер success-экранов).

    В отличие от handle_sbp_recurring_enable подписка берётся по id из
    callback_data: в multi-tariff режиме контекстное разрешение может выбрать
    не ту подписку, а ошибиться в привязке денежного автоплатежа нельзя.
    Дальше — тот же флоу, что у кнопки в меню автоплатежа.
    """
    texts = get_texts(db_user.language)

    if not settings.is_platega_recurrent_enabled():
        await callback.answer(
            texts.t('SBP_RECURRING_UNAVAILABLE', '⚠️ Автопродление через СБП сейчас недоступно'),
            show_alert=True,
        )
        return

    try:
        target_id = int(callback.data.split(':', 1)[1])
    except (IndexError, ValueError):
        await callback.answer(texts.t('INVALID_REQUEST', 'Invalid request'), show_alert=True)
        return

    from app.database.crud.subscription import get_subscription_by_id

    subscription = await get_subscription_by_id(db, target_id)
    if not subscription or subscription.user_id != db_user.id:
        await callback.answer(
            texts.t('SUBSCRIPTION_ACTIVE_REQUIRED', '⚠️ У вас нет активной подписки!'),
            show_alert=True,
        )
        return

    # Trial cannot authorize a real recurring bank payment (same guard as the
    # menu enable path).
    if subscription.is_trial or subscription.is_trial is None:
        await callback.answer(
            texts.t('AUTOPAY_NOT_AVAILABLE_TRIAL', 'Автоплатеж недоступен для пробных подписок.'),
            show_alert=True,
        )
        return

    try:
        await db.refresh(subscription, ['tariff'])
    except Exception:
        logger.warning('Ignored error in handle_sbp_recurring_enable_for', exc_info=True)

    tariff = subscription.tariff
    if tariff is None:
        await callback.answer(
            texts.t(
                'SBP_RECURRING_NO_TARIFF',
                '⚠️ Автопродление через СБП доступно только для подписок с тарифом.',
            ),
            show_alert=True,
        )
        return

    reply = _OneShotCallbackReply(callback)

    # n2: предупреждение о смене движка:
    # баланс-автоплатёж этой подписки будут отключены при создании
    # СБП-привязки — предупреждаем alert'ом, флоу не прерываем.
    try:
        from app.services.recurrent_amount import get_active_recurrent_engines, recurrent_engines_warning

        _engines = await get_active_recurrent_engines(db, subscription)
        _warning = recurrent_engines_warning(texts, _engines, enabling='platega')
        if _warning:
            await reply.alert(_warning)
    except Exception:
        logger.warning('Ignored error in handle_sbp_recurring_enable_for', exc_info=True)

    from app.services.payment.platega import enable_platega_sbp_recurring

    # Если предупреждение о смене способа уже ответило на нажатие, ошибки ниже
    # уходят сообщением (reply.alert) — иначе их не было бы видно.
    try:
        result = await enable_platega_sbp_recurring(db, user_id=db_user.id, subscription=subscription, tariff=tariff)
    except ValueError as error:
        # ValueError — осмысленная причина (период/цена/состояние подписки),
        # показываем её пользователю как есть вместо общей «попробуйте позже».
        await reply.alert(str(error), escape=True)
        return
    except RuntimeError as error:
        logger.warning(
            'Не удалось подключить СБП-автопродление (оффер success-экрана)',
            error=str(error),
            subscription_id=subscription.id,
        )
        await reply.alert(
            texts.t(
                'SBP_RECURRING_ENABLE_ERROR',
                '❌ Не удалось подключить автопродление через СБП. Попробуйте позже.',
            )
        )
        return

    redirect_url = result.get('redirect_url')
    if not redirect_url:
        # Идемпотентный повтор по уже живой привязке без сохранённой ссылки.
        await reply.alert(
            texts.t('SBP_RECURRING_ALREADY_ACTIVE', 'СБП-автопродление уже подключено.'), show_alert=False
        )
        return

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('SBP_RECURRING_CONFIRM_BUTTON', '🏦 Подтвердить в банке'),
                    url=redirect_url,
                )
            ],
            [types.InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')],
        ]
    )

    # n7: точка входа может быть медиа-рассылкой (кнопка из broadcast'а) —
    # edit_text по фото упадёт; edit_or_answer_photo сам выберет caption/текст.
    await edit_or_answer_photo(
        callback,
        texts.t(
            'SBP_RECURRING_ENABLE_SUCCESS',
            '⚡ <b>Автопродление через СБП</b>\n\n'
            'Подтвердите подключение в банковском приложении по кнопке ниже.\n'
            'После подтверждения автопродление станет активным.',
        )
        # Сумма и шаг списания — ДО формы банка: юзер видит «270 ₽ каждые
        # 30 дн.» в боте, а не только на форме Platega (первое списание
        # происходит сразу при подтверждении привязки — честно предупреждаем).
        + texts.t(
            'SBP_RECURRING_PRICE_LINE',
            '\n\n💰 <b>{amount}</b> каждые {days} дн. — первое списание сразу при подтверждении.',
        ).format(
            amount=f'{(result.get("amount_kopeks") or 0) // 100} ₽',
            days=result.get('charge_days') or 30,
        ),
        keyboard,
    )
    await reply.done()


async def handle_sbp_recurring_cancel(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None
):
    """Шаг подтверждения отмены СБП-автопродления (удержание): одно случайное
    нажатие больше не снимает привязку — сначала показываем, что останется без
    автосписаний, и первой даём кнопку «Оставить автопродление»."""
    texts = get_texts(db_user.language)
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('SBP_RECURRING_KEEP_BUTTON', '✅ Оставить автопродление'),
                    callback_data='sbp_recurring_menu',
                    style='success',
                )
            ],
            [
                types.InlineKeyboardButton(
                    text=texts.t('SBP_RECURRING_CANCEL_CONFIRM_BUTTON', '❌ Да, отменить'),
                    callback_data='sbp_recurring_cancel_confirm',
                )
            ],
        ]
    )
    await callback.message.edit_text(
        texts.t(
            'SBP_RECURRING_CANCEL_CONFIRM_TEXT',
            '❓ <b>Отменить автопродление через СБП?</b>\n\n'
            'Подписка останется активной до конца оплаченного периода, '
            'но автосписания прекратятся — продлевать нужно будет вручную.',
        ),
        reply_markup=keyboard,
        parse_mode='HTML',
    )
    await callback.answer()


async def handle_sbp_recurring_cancel_confirm(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext = None
):
    """Отменить активное СБП-автопродление и обновить статус-вью.

    НЕ гейтится PLATEGA_RECURRENT_ENABLED намеренно (паритет с кабинетным
    cancel-эндпоинтом): отмена — операция безопасности. Выключение фичи при
    живых привязках не останавливает списания Platega — юзер с существующей
    кнопкой отмены обязан иметь путь отписаться с любой поверхности.
    """
    texts = get_texts(db_user.language)

    subscription, sub_id = await _resolve_subscription(callback, db_user, db, state)
    if not subscription:
        await callback.answer(
            texts.t('SUBSCRIPTION_ACTIVE_REQUIRED', '⚠️ У вас нет активной подписки!'),
            show_alert=True,
        )
        return

    from app.services.payment.platega import cancel_platega_recurring_for_subscription_safe

    await cancel_platega_recurring_for_subscription_safe(db, subscription.id)
    await callback.answer(texts.t('SBP_RECURRING_CANCELLED', '✅ Автопродление через СБП отменено'))
    # Меню гейтится флагом — при выключенной фиче не дёргаем его, чтобы после
    # успешной отмены юзер не получил второй алерт «недоступно».
    if settings.is_platega_recurrent_enabled():
        await handle_sbp_recurring_menu(callback, db_user, db, state)


async def handle_subscription_cancel(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    get_texts(db_user.language)

    await state.clear()

    # Multi-tariff safe: delete only the cart for the current subscription
    # to avoid nuking carts belonging to other subscriptions.
    cart_data = await user_cart_service.get_user_cart(db_user.id)
    cart_sub_id = None
    if cart_data:
        try:
            raw = cart_data.get('subscription_id')
            if raw is not None:
                cart_sub_id = int(raw)
        except (TypeError, ValueError):
            pass

    if cart_sub_id is not None:
        await user_cart_service.delete_subscription_cart(db_user.id, cart_sub_id)
        # Clean up global key only if it still references this subscription
        global_cart = await user_cart_service.get_user_cart(db_user.id)
        if global_cart and global_cart.get('subscription_id') is not None:
            try:
                if int(global_cart['subscription_id']) == cart_sub_id:
                    await user_cart_service.delete_global_cart_only(db_user.id)
            except (TypeError, ValueError):
                pass
    else:
        # No subscription_id in cart -- safe to delete the global cart
        await user_cart_service.delete_user_cart(db_user.id)

    from app.handlers.menu import show_main_menu

    await show_main_menu(callback, db_user, db)

    await callback.answer('❌ Покупка отменена')
