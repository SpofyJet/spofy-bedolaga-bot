import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.localization.texts import get_texts
from app.utils.pagination import build_page_nav_row


def _t(texts, key: str, default: str) -> str:
    """Helper for localized button labels with fallbacks."""
    return texts.t(key, default)


def get_admin_main_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAIN_USERS_SUBSCRIPTIONS', '👥 Юзеры/Подписки'),
                    callback_data='admin_submenu_users',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAIN_PROMO_STATS', '💰 Промокоды/Кампании'),
                    callback_data='admin_submenu_promo',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAIN_SUPPORT', '🛟 Поддержка'),
                    callback_data='admin_submenu_support',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAIN_MESSAGES', '📨 Сообщения'),
                    callback_data='admin_submenu_communications',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_SETTINGS_MAINTENANCE', '🔧 Техработы'),
                    callback_data='maintenance_panel',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAIN_SYSTEM', '🛠️ Система'),
                    callback_data='admin_submenu_system',
                ),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')],
        ]
    )


def get_admin_users_submenu_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.ADMIN_USERS, callback_data='admin_users'),
                InlineKeyboardButton(text=texts.ADMIN_REFERRALS, callback_data='admin_referrals'),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_panel')],
        ]
    )


def get_admin_promo_submenu_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.ADMIN_PROMOCODES, callback_data='admin_promocodes'),
                InlineKeyboardButton(text=texts.ADMIN_CAMPAIGNS, callback_data='admin_campaigns'),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_panel')],
        ]
    )


def get_admin_communications_submenu_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.ADMIN_MESSAGES, callback_data='admin_messages')],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_COMMUNICATIONS_PROMO_OFFERS', '🎯 Промо-предложения'),
                    callback_data='admin_promo_offers',
                )
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_panel')],
        ]
    )


def get_admin_support_submenu_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_SUPPORT_TICKETS', '🎫 Тикеты поддержки'), callback_data='admin_tickets'
                )
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_panel')],
        ]
    )


def get_admin_system_submenu_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(texts, 'ADMIN_SYSTEM_LOGS', '🧾 Логи'), callback_data='admin_system_logs')],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_panel')],
        ]
    )


def get_admin_users_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USERS_ALL', '👥 Все пользователи'), callback_data='admin_users_list'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USERS_SEARCH', '🔍 Поиск'), callback_data='admin_users_search'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USERS_BLOCKED_CHECK', '🔒 Заблокировавшие бота'),
                    callback_data='admin_blocked_users',
                )
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_submenu_users')],
        ]
    )


def get_admin_promocodes_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODES_ALL', '🎫 Все промокоды'), callback_data='admin_promo_list'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODES_CREATE', '➕ Создать'), callback_data='admin_promo_create'
                ),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_submenu_promo')],
        ]
    )


def get_admin_campaigns_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CAMPAIGNS_LIST', '📋 Список кампаний'), callback_data='admin_campaigns_list'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CAMPAIGNS_CREATE', '➕ Создать'), callback_data='admin_campaigns_create'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CAMPAIGNS_GENERAL_STATS', '📊 Общая статистика'),
                    callback_data='admin_campaigns_stats',
                )
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_submenu_promo')],
        ]
    )


def get_campaign_management_keyboard(campaign_id: int, is_active: bool, language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CAMPAIGN_STATS', '📊 Статистика'),
                    callback_data=f'admin_campaign_stats_{campaign_id}',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BACK_TO_LIST', '⬅️ К списку'), callback_data='admin_campaigns_list'
                )
            ],
        ]
    )


def get_campaign_bonus_type_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CAMPAIGN_BONUS_BALANCE', '💰 Бонус на баланс'),
                    callback_data='campaign_bonus_balance',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CAMPAIGN_BONUS_NONE', '🔗 Только ссылка'), callback_data='campaign_bonus_none'
                ),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_campaigns')],
        ]
    )


def get_admin_messages_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MESSAGES_BY_SUBSCRIPTIONS', '🎯 Всем или по подпискам'),
                    callback_data='admin_msg_by_sub',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MESSAGES_BY_CRITERIA', '🔍 По критериям'), callback_data='admin_msg_custom'
                ),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_submenu_communications')],
        ]
    )


def get_user_management_keyboard(
    user_id: int, user_status: str, language: str = 'ru', back_callback: str = 'admin_users_list'
) -> InlineKeyboardMarkup:
    texts = get_texts(language)

    keyboard = [
        [
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_USER_BALANCE', '💰 Баланс'), callback_data=f'admin_user_balance_{user_id}'
            ),
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_USER_SUBSCRIPTION_SETTINGS', '📱 Подписка и настройки'),
                callback_data=f'admin_user_subscription_{user_id}',
            ),
        ],
        [
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_USER_REFERRALS_BUTTON', '🤝 Рефералы'),
                callback_data=f'admin_user_referrals_{user_id}',
            )
        ],
        [
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_USER_TRANSACTIONS', '📋 Транзакции'),
                callback_data=f'admin_user_transactions_{user_id}',
            )
        ],
    ]

    # Кнопка управления ограничениями
    keyboard.append(
        [
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_USER_RESTRICTIONS', '⚠️ Ограничить'),
                callback_data=f'admin_user_restrictions_{user_id}',
            )
        ]
    )

    if user_status == 'active':
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USER_BLOCK', '🚫 Заблокировать'), callback_data=f'admin_user_block_{user_id}'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USER_DELETE', '🗑️ Удалить'), callback_data=f'admin_user_delete_{user_id}'
                ),
            ]
        )
    elif user_status == 'blocked':
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USER_UNBLOCK', '✅ Разблокировать'),
                    callback_data=f'admin_user_unblock_{user_id}',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USER_DELETE', '🗑️ Удалить'), callback_data=f'admin_user_delete_{user_id}'
                ),
            ]
        )
    elif user_status == 'deleted':
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_USER_ALREADY_DELETED', '❌ Пользователь удален'), callback_data='noop'
                )
            ]
        )

    keyboard.append([InlineKeyboardButton(text=texts.BACK, callback_data=back_callback)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_user_restrictions_keyboard(
    user_id: int, restriction_topup: bool, restriction_subscription: bool, language: str = 'ru'
) -> InlineKeyboardMarkup:
    """Клавиатура управления ограничениями пользователя."""
    texts = get_texts(language)

    keyboard = []

    # Toggle для ограничения пополнения
    topup_emoji = '🚫' if restriction_topup else '✅'
    topup_text = f'{topup_emoji} Пополнение'
    keyboard.append(
        [InlineKeyboardButton(text=topup_text, callback_data=f'admin_user_restriction_toggle_topup_{user_id}')]
    )

    # Toggle для ограничения подписки
    sub_emoji = '🚫' if restriction_subscription else '✅'
    sub_text = f'{sub_emoji} Продление/покупка'
    keyboard.append([InlineKeyboardButton(text=sub_text, callback_data=f'admin_user_restriction_toggle_sub_{user_id}')])

    # Кнопка изменения причины
    keyboard.append(
        [InlineKeyboardButton(text='📝 Изменить причину', callback_data=f'admin_user_restriction_reason_{user_id}')]
    )

    # Кнопка снятия всех ограничений (если есть хотя бы одно)
    if restriction_topup or restriction_subscription:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text='🔓 Снять все ограничения', callback_data=f'admin_user_restriction_clear_{user_id}'
                )
            ]
        )

    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text=texts.BACK, callback_data=f'admin_user_manage_{user_id}')])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_confirmation_keyboard(
    confirm_action: str, cancel_action: str = 'admin_panel', language: str = 'ru'
) -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.YES, callback_data=confirm_action),
                InlineKeyboardButton(text=texts.NO, callback_data=cancel_action),
            ]
        ]
    )


def get_promocode_type_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODE_TYPE_BALANCE', '💰 Баланс'), callback_data='promo_type_balance'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODE_TYPE_DAYS', '📅 Дни подписки'), callback_data='promo_type_days'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODE_TYPE_TRIAL', '🎁 Триал'), callback_data='promo_type_trial'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODE_TYPE_DISCOUNT', '💸 Одноразовая скидка'),
                    callback_data='promo_type_discount',
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_PROMOCODE_TYPE_BALANCE_DAYS', '💰📅 Баланс + дни'),
                    callback_data='promo_type_combo',
                )
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_promocodes')],
        ]
    )


def get_broadcast_target_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_ALL', '👥 Всем'), callback_data='broadcast_all'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_ACTIVE', '📱 С подпиской'), callback_data='broadcast_active'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_TRIAL', '🎁 Триал'), callback_data='broadcast_trial'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_NO_SUB', '❌ Без подписки'), callback_data='broadcast_no_sub'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_EXPIRING', '⏰ Истекающие'),
                    callback_data='broadcast_expiring',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_EXPIRED', '🔚 Истекшие'), callback_data='broadcast_expired'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_ACTIVE_ZERO', '🧊 Активна 0 ГБ'),
                    callback_data='broadcast_active_zero',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_TARGET_TRIAL_ZERO', '🥶 Триал 0 ГБ'),
                    callback_data='broadcast_trial_zero',
                ),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_messages')],
        ]
    )


def get_custom_criteria_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_TODAY', '📅 Сегодня'), callback_data='criteria_today'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_WEEK', '📅 За неделю'), callback_data='criteria_week'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_MONTH', '📅 За месяц'), callback_data='criteria_month'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_ACTIVE_TODAY', '⚡ Активные сегодня'),
                    callback_data='criteria_active_today',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_INACTIVE_WEEK', '💤 Неактивные 7+ дней'),
                    callback_data='criteria_inactive_week',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_INACTIVE_MONTH', '💤 Неактивные 30+ дней'),
                    callback_data='criteria_inactive_month',
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_REFERRALS', '🤝 Через рефералов'), callback_data='criteria_referrals'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_CRITERIA_DIRECT', '🎯 Прямая регистрация'), callback_data='criteria_direct'
                ),
            ],
            [InlineKeyboardButton(text=texts.BACK, callback_data='admin_messages')],
        ]
    )


def get_admin_pagination_keyboard(
    current_page: int, total_pages: int, callback_prefix: str, back_callback: str = 'admin_panel', language: str = 'ru'
) -> InlineKeyboardMarkup:
    texts = get_texts(language)
    keyboard = []

    if total_pages > 1:
        keyboard.append(build_page_nav_row(current_page, total_pages, f'{callback_prefix}_page_'))

    keyboard.append([InlineKeyboardButton(text=texts.BACK, callback_data=back_callback)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_maintenance_keyboard(
    language: str, is_maintenance_active: bool, is_monitoring_active: bool, panel_has_issues: bool = False
) -> InlineKeyboardMarkup:
    texts = get_texts(language)
    keyboard = []

    if is_maintenance_active:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAINTENANCE_DISABLE', '🟢 Выключить техработы'),
                    callback_data='maintenance_toggle',
                )
            ]
        )
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAINTENANCE_ENABLE', '🔧 Включить техработы'),
                    callback_data='maintenance_toggle',
                )
            ]
        )

    if is_monitoring_active:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAINTENANCE_STOP_MONITORING', '⏹️ Остановить мониторинг'),
                    callback_data='maintenance_monitoring',
                )
            ]
        )
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_MAINTENANCE_START_MONITORING', '▶️ Запустить мониторинг'),
                    callback_data='maintenance_monitoring',
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_MAINTENANCE_CHECK_API', '🔍 Проверить API'), callback_data='maintenance_check_api'
            ),
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_MAINTENANCE_PANEL_STATUS', '🌐 Статус панели')
                + ('⚠️' if panel_has_issues else ''),
                callback_data='maintenance_check_panel',
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                text=_t(texts, 'ADMIN_MAINTENANCE_SEND_NOTIFICATION', '📢 Отправить уведомление'),
                callback_data='maintenance_manual_notify',
            )
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(text=_t(texts, 'ADMIN_REFRESH', '🔄 Обновить'), callback_data='maintenance_panel'),
            InlineKeyboardButton(text=texts.BACK, callback_data='admin_panel'),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Иконка в начале подписи кнопки: премиум-тег целиком или обычный эмодзи до пробела.
_LEADING_ICON_RE = re.compile(r'^\s*(?:<tg-emoji\b[^>]*>.*?</tg-emoji>|\S+)\s+', re.DOTALL)


DEFAULT_BROADCAST_BUTTONS = ('home',)

BROADCAST_BUTTONS = {
    'balance': {
        'default_text': '💰 Пополнить баланс',
        'text_key': 'ADMIN_BROADCAST_BUTTON_BALANCE',
        'callback': 'balance_topup',
    },
    'referrals': {
        'default_text': '🤝 Партнерка',
        'text_key': 'ADMIN_BROADCAST_BUTTON_REFERRALS',
        'callback': 'menu_referrals',
    },
    'promocode': {
        'default_text': '🎫 Промокод',
        'text_key': 'ADMIN_BROADCAST_BUTTON_PROMOCODE',
        'callback': 'menu_promocode',
    },
    'connect': {
        'default_text': '🔗 Подключиться',
        'text_key': 'ADMIN_BROADCAST_BUTTON_CONNECT',
        'callback': 'subscription_connect',
    },
    'subscription': {
        'default_text': '📱 Подписка',
        'text_key': 'ADMIN_BROADCAST_BUTTON_SUBSCRIPTION',
        'callback': 'menu_subscription',
    },
    'support': {
        'default_text': '🛠️ Техподдержка',
        'text_key': 'ADMIN_BROADCAST_BUTTON_SUPPORT',
        'callback': 'menu_support',
    },
    'home': {
        'default_text': '🏠 На главную',
        'text_key': 'ADMIN_BROADCAST_BUTTON_HOME',
        'callback': 'back_to_menu',
    },
}

BROADCAST_BUTTON_ROWS: tuple[tuple[str, ...], ...] = (
    ('balance', 'referrals'),
    ('promocode', 'connect'),
    ('subscription', 'support'),
    ('home',),
)


def get_broadcast_button_config(language: str) -> dict[str, dict[str, str]]:
    texts = get_texts(language)
    return {
        key: {
            'text': texts.t(config['text_key'], config['default_text']),
            'callback': config['callback'],
        }
        for key, config in BROADCAST_BUTTONS.items()
    }


def get_broadcast_button_labels(language: str) -> dict[str, str]:
    return {key: value['text'] for key, value in get_broadcast_button_config(language).items()}


def get_broadcast_media_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_ADD_PHOTO', '📷 Добавить фото'), callback_data='add_media_photo'
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_ADD_VIDEO', '🎥 Добавить видео'), callback_data='add_media_video'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_ADD_DOCUMENT', '📄 Добавить документ'),
                    callback_data='add_media_document',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_SKIP_MEDIA', '⏭️ Пропустить медиа'), callback_data='skip_media'
                ),
            ],
            [InlineKeyboardButton(text=_t(texts, 'ADMIN_CANCEL', '❌ Отмена'), callback_data='admin_messages')],
        ]
    )


def get_media_confirm_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_USE_MEDIA', '✅ Использовать это медиа'),
                    callback_data='confirm_media',
                ),
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_REPLACE_MEDIA', '🔄 Заменить медиа'), callback_data='replace_media'
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_NO_MEDIA', '⏭️ Без медиа'), callback_data='skip_media'
                ),
                InlineKeyboardButton(text=_t(texts, 'ADMIN_CANCEL', '❌ Отмена'), callback_data='admin_messages'),
            ],
        ]
    )


def get_updated_message_buttons_selector_keyboard_with_media(
    selected_buttons: list, has_media: bool = False, language: str = 'ru'
) -> InlineKeyboardMarkup:
    selected_buttons = selected_buttons or []

    texts = get_texts(language)
    button_config_map = get_broadcast_button_config(language)
    keyboard: list[list[InlineKeyboardButton]] = []

    for row in BROADCAST_BUTTON_ROWS:
        row_buttons: list[InlineKeyboardButton] = []
        for button_key in row:
            button_config = button_config_map[button_key]
            base_text = button_config['text']
            if button_key in selected_buttons:
                # Галочка вместо иконки кнопки. Иконка в локали — целый тег <tg-emoji …>…</tg-emoji>
                # с пробелом внутри: резать по первому пробелу нельзя, на кнопке оставался обрубок тега.
                toggle_text = f'✅ {_LEADING_ICON_RE.sub("", base_text, count=1)}'
            else:
                toggle_text = base_text
            row_buttons.append(InlineKeyboardButton(text=toggle_text, callback_data=f'btn_{button_key}'))
        if row_buttons:
            keyboard.append(row_buttons)

    if has_media:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=_t(texts, 'ADMIN_BROADCAST_CHANGE_MEDIA', '🖼️ Изменить медиа'), callback_data='change_media'
                )
            ]
        )

    keyboard.extend(
        [
            [InlineKeyboardButton(text=_t(texts, 'ADMIN_CONTINUE', '✅ Продолжить'), callback_data='buttons_confirm')],
            [InlineKeyboardButton(text=_t(texts, 'ADMIN_CANCEL', '❌ Отмена'), callback_data='admin_messages')],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
