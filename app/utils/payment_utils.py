from app.config import settings
from app.localization.texts import get_texts


def get_available_payment_methods() -> list[dict[str, str]]:
    """
    Возвращает список доступных способов оплаты с их настройками
    """
    methods = []

    if settings.TELEGRAM_STARS_ENABLED:
        methods.append(
            {
                'id': 'stars',
                'name': 'Telegram Stars',
                'icon': '⭐',
                'description': 'быстро и удобно',
                'callback': 'topup_stars',
            }
        )

    if settings.is_wata_enabled():
        methods.append(
            {
                'id': 'wata',
                'name': 'Банковская карта',
                'icon': '💳',
                'description': 'через WATA',
                'callback': 'topup_wata',
            }
        )

    if settings.is_cryptobot_enabled():
        methods.append(
            {
                'id': 'cryptobot',
                'name': 'Криптовалюта',
                'icon': '🪙',
                'description': 'через CryptoBot',
                'callback': 'topup_cryptobot',
            }
        )

    if settings.is_xrocket_enabled():
        methods.append(
            {
                'id': 'xrocket',
                'name': 'Криптовалюта',
                'icon': '🚀',
                'description': 'через xRocket',
                'callback': 'topup_xrocket',
            }
        )

    if settings.is_pay2328_enabled():
        methods.append(
            {
                'id': 'pay2328',
                'name': 'Криптовалюта',
                'icon': '🪙',
                'description': 'через 2328.io',
                'callback': 'topup_pay2328',
            }
        )

    if settings.is_platega_enabled() and settings.get_platega_active_methods():
        platega_name = settings.get_platega_display_name()
        if settings.PLATEGA_INLINE_METHODS:
            for method_code in settings.get_platega_active_methods():
                info = settings.get_platega_method_definitions().get(method_code, {})
                methods.append(
                    {
                        'id': f'platega_m{method_code}',
                        'name': info.get('name', f'Метод {method_code}'),
                        'icon': info.get('title', '💳').split(' ', 1)[0] if info.get('title') else '💳',
                        'description': f'через {platega_name}',
                        'callback': f'topup_platega_m{method_code}',
                    }
                )
        else:
            methods.append(
                {
                    'id': 'platega',
                    'name': 'Банковская карта',
                    'icon': '💳',
                    'description': f'через {platega_name} (карты + СБП)',
                    'callback': 'topup_platega',
                }
            )

    if settings.is_support_topup_enabled():
        methods.append(
            {
                'id': 'support',
                'name': 'Через поддержку',
                'icon': '🛠️',
                'description': 'другие способы',
                'callback': 'topup_support',
            }
        )

    return methods


def get_payment_methods_text(language: str) -> str:
    """
    Генерирует текст с описанием доступных способов оплаты
    """
    texts = get_texts(language)
    methods = get_available_payment_methods()

    if not methods:
        return texts.t(
            'PAYMENT_METHODS_NONE_AVAILABLE',
            """<b>Способы пополнения баланса</b>

⚠️ В данный момент способы оплаты временно недоступны.
Попробуйте позже.

Выберите способ пополнения:""",
        )

    if len(methods) == 1 and methods[0]['id'] == 'support':
        return texts.t(
            'PAYMENT_METHODS_ONLY_SUPPORT',
            """<b>Способы пополнения баланса</b>

⚠️ В данный момент автоматические способы оплаты временно недоступны.
Обратитесь в техподдержку для пополнения баланса.

Выберите способ пополнения:""",
        )

    text = (
        texts.t(
            'PAYMENT_METHODS_TITLE',
            '<b>Способы пополнения баланса</b>',
        )
        + '\n\n'
    )
    text += (
        texts.t(
            'PAYMENT_METHODS_PROMPT',
            'Выберите удобный для вас способ оплаты:',
        )
        + '\n\n'
    )

    return text
