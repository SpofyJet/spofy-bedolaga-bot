"""Значки кнопок подобраны по картинке: у разных по смыслу символов значок не общий.

До 13.11.2026 id брали по подписи в наборе, и на кнопках стояло не то: под «👥» и «🤝»
одна сезонная картинка, под «💸» и «💵» — знак доллара, у «📱 Подписка» — макет окна
с боковой панелью. Часть кнопок («🛒 Продолжить оформление», «🧾 История», «✖️ Закрыть»)
оставалась без значка вовсе.
"""

import json
import re
from pathlib import Path

from app.keyboards.button_icons import BUTTON_ICONS, _icon_for


ROOT = Path(__file__).resolve().parents[1]

# Символы-синонимы: им положен один значок.
SYNONYMS = [
    {'⭐️', '⭐'},
    {'⚡️', '⚡', '🚀'},
    {'⏳', '⌛'},
    {'💰', '👛'},
    {'🎟️', '🎟', '🎫'},
    {'📢', '📣'},
    {'📨', '📬'},
    {'🛟', '🆘', '🙋'},
    {'⬅️', '⬅', '◀️', '↩️'},
    {'👁️', '👁'},
    {'❌', '✖️', '✖'},
    {'ℹ️', 'ℹ'},
    {'🗑️', '🗑'},
    {'⚙️', '⚙'},
    {'🛠️', '🛠', '🔧'},
    {'🛡️', '🛡'},
    {'🏆', '🥇'},
    {'🍏', '🍎'},
    {'🏴\u200d☠️', '🏴\u200d☠'},
]


def test_one_icon_is_not_shared_by_unrelated_symbols() -> None:
    by_icon: dict[str, set[str]] = {}
    for symbol, icon in BUTTON_ICONS.items():
        by_icon.setdefault(icon, set()).add(symbol)
    shared = [symbols for symbols in by_icon.values() if len(symbols) > 1]
    assert [symbols for symbols in shared if not any(symbols <= group for group in SYNONYMS)] == []


def test_colour_statuses_stay_emoji() -> None:
    # Одноцветный значок теряет смысл цвета: «🔴 Открытые обращения» / «🟢 Закрытые обращения».
    assert not {'🔴', '🟢', '🟡', '🟠', '⚫'} & set(BUTTON_ICONS)


def test_most_pressed_buttons_have_icons() -> None:
    # Самые нажимаемые кнопки за 30 дней до 13.11.2026 (button_click_logs).
    values = json.loads((ROOT / 'app/localization/locales/ru.json').read_text(encoding='utf-8'))
    keys = [
        'MENU_SUBSCRIPTION',
        'SUB_DEVICES_BUTTON',
        'MENU_BUY_SUBSCRIPTION',
        'MENU_EXTEND_SUBSCRIPTION',
        'BALANCE_TOPUP',
        'RETURN_TO_SUBSCRIPTION_CHECKOUT',
        'CHECK_STATUS_BUTTON',
        'BALANCE_HISTORY',
        'WEBHOOK_CLOSE_BUTTON',
        'MENU_REFERRALS',
        'MENU_SUPPORT',
        'CONNECT_BUTTON',
        'MANAGE_DEVICES_BUTTON',
        'CREATE_TICKET_BUTTON',
        'MAIN_MENU_BUTTON',
    ]
    without = {key: values[key] for key in keys if _icon_for(values[key]) is None}
    assert without == {}


def test_payment_method_buttons_have_icons() -> None:
    # До 13.11.2026 значок был у «Карта / СБП», «Telegram Stars» и «СБП (WATA)», а «Международные карты»,
    # «Криптовалюта (xRocket)», «Криптовалюта (2328.io)» и «Другие способы» в том же списке стояли без него.
    keys = [
        'PAYMENT_PLATEGA_M2',
        'PAYMENT_PLATEGA_M11',
        'PAYMENT_PLATEGA_M12',
        'PAYMENT_PLATEGA_M13',
        'PAYMENT_TELEGRAM_STARS',
        'PAYMENT_CARD_WATA',
        'PAYMENT_XROCKET',
        'PAYMENT_PAY2328',
        'PAYMENT_CRYPTOBOT',
        'PAYMENT_VIA_SUPPORT',
    ]
    for locale in ('ru', 'en'):
        values = json.loads((ROOT / f'app/localization/locales/{locale}.json').read_text(encoding='utf-8'))
        without = {key: values[key] for key in keys if _icon_for(values[key]) is None}
        assert without == {}, locale


def test_payment_methods_of_one_kind_share_an_icon_and_kinds_differ() -> None:
    values = json.loads((ROOT / 'app/localization/locales/ru.json').read_text(encoding='utf-8'))

    def icon(key: str) -> str:
        return _icon_for(values[key])[1]

    assert icon('PAYMENT_XROCKET') == icon('PAYMENT_PAY2328') == icon('PAYMENT_CRYPTOBOT')
    kinds = [
        icon(key)
        for key in (
            'PAYMENT_PLATEGA_M2',
            'PAYMENT_PLATEGA_M12',
            'PAYMENT_TELEGRAM_STARS',
            'PAYMENT_CARD_WATA',
            'PAYMENT_XROCKET',
            'PAYMENT_VIA_SUPPORT',
        )
    ]
    assert len(set(kinds)) == len(kinds)


def test_bypass_tariff_button_carries_the_bypass_sign() -> None:
    # Название тарифа приходит из базы. Рядом «⭐️ Стандартный» и «👑 ULTIMA» со значками, а «🏴‍☠️ С Обходами»
    # (433 нажатия за 30 дней до 13.11.2026) оставался с обычным флагом. Знак обходов — щит Spofy, как в текстах.
    values = json.loads((ROOT / 'app/localization/locales/ru.json').read_text(encoding='utf-8'))
    in_texts = re.search(r"<tg-emoji emoji-id='(\d+)'>🏴\u200d☠️</tg-emoji>", values['BYPASS_SUSPENDED']).group(1)
    assert _icon_for('🏴\u200d☠️ С Обходами') == ('С Обходами', in_texts)
    assert _icon_for('🏴\u200d☠️ С Обходами (+44₽)') == ('С Обходами (+44₽)', in_texts)
    assert _icon_for('⭐️ Стандартный')[0] == 'Стандартный'
    assert _icon_for('👑 ULTIMA')[0] == 'ULTIMA'


def test_check_status_is_not_a_chart() -> None:
    values = json.loads((ROOT / 'app/localization/locales/ru.json').read_text(encoding='utf-8'))
    text, icon = _icon_for(values['CHECK_STATUS_BUTTON'])
    assert text == 'Проверить статус'
    assert icon == BUTTON_ICONS['🔄'] != BUTTON_ICONS['📊']


def test_single_emoji_buttons_are_left_alone() -> None:
    assert _icon_for('➡️') is None
    assert _icon_for('⬅️') is None


def test_all_icon_ids_look_like_custom_emoji_ids() -> None:
    assert [icon for icon in BUTTON_ICONS.values() if not re.fullmatch(r'\d{18,20}', icon)] == []
