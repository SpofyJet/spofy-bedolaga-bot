"""«Навсегда»: бессрочная подписка (ULTIMA).

Бессрочный тариф продаётся как период в 2222 дня, но пользователю это число ничего
не говорит, а через шесть лет подписка всё равно истекла бы. Поэтому:

* период от ``LIFETIME_MIN_DAYS`` дней считается бессрочным и везде показывается
  как «Навсегда»;
* дата окончания такой подписки — ``LIFETIME_END`` (31.12.2099). Модель Subscription
  сама приводит к ней любую дату дальше ``LIFETIME_MIN_DAYS`` от текущего момента,
  поэтому покупка, переход на тариф, продление, админка и вебхуки панели
  дают одну и ту же отметку без отдельных правок в каждом пути;
* остаток дней и дата окончания бессрочной подписки тоже показываются как
  «Навсегда», а не «осталось 26 000 дн.» и не «до 31.12.2099».

Модуль не импортирует ничего из app, чтобы его можно было звать из моделей.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime


# Около 5,5 года. Обычные периоды не дольше года, у ULTIMA 2222 дня.
LIFETIME_MIN_DAYS = 2000
LIFETIME_END = datetime(2099, 12, 31, 23, 59, 59, tzinfo=UTC)
# Всё, что кончается позже этой даты, показываем как «Навсегда»: и наши 2099, и
# даты, которые панель или админ могли поставить ещё дальше.
_LIFETIME_DISPLAY_FROM = datetime(2090, 1, 1, tzinfo=UTC)

_LABELS = {
    'ru': 'Навсегда',
    'en': 'Forever',
    'ua': 'Назавжди',
    'uk': 'Назавжди',
    'zh': '永久',
    'fa': 'دائمی',
}


def _lang(language: str | None) -> str:
    return (language or 'ru').split('-')[0].lower()


def lifetime_label(language: str | None = 'ru') -> str:
    """«Навсегда» на языке пользователя (с заглавной: годится и для кнопки, и после «Период:»)."""
    return _LABELS.get(_lang(language), _LABELS['en'])


def is_lifetime_period(days) -> bool:
    try:
        return int(days) >= LIFETIME_MIN_DAYS
    except (TypeError, ValueError):
        return False


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def is_lifetime_end(end_date: datetime | None) -> bool:
    """Дата окончания бессрочной подписки."""
    if not isinstance(end_date, datetime):
        return False
    return _aware(end_date) >= _LIFETIME_DISPLAY_FROM


def is_lifetime_subscription(subscription) -> bool:
    return is_lifetime_end(getattr(subscription, 'end_date', None))


def normalize_end_date(value: datetime | None, now: datetime | None = None) -> datetime | None:
    """Дата дальше LIFETIME_MIN_DAYS от текущего момента приводится к LIFETIME_END.

    Иначе каждая докупка или переход на ULTIMA сдвигали бы дату (2099 + 2222 дня),
    а срок «со скидкой на остаток» давал бы 2032 год вместо «навсегда».
    """
    if not isinstance(value, datetime):
        return value
    aware = _aware(value)
    current = _aware(now) if now else datetime.now(UTC)
    if (aware - current).days >= LIFETIME_MIN_DAYS:
        return LIFETIME_END
    return value


def period_phrase(days: int, language: str | None = 'ru') -> str | None:
    """«навсегда» для описаний вида «Покупка тарифа X навсегда» (вместо «на 2222 дня»).

    Возвращает None для обычного периода — тогда вызывающий пишет «на N дней» сам.
    """
    if not is_lifetime_period(days):
        return None
    return lifetime_label(language).lower() if _lang(language) in {'ru', 'ua', 'uk', 'en'} else lifetime_label(language)


_UNIT_RE = r'(?:дн\.|дней|дня|день|днів|days?|d\.|天|روز)'
_PREP_RE = r'(?P<prep>на |for |为期\s*|به مدت )?'


def apply_lifetime_period(template: str, days, placeholder: str = 'period_days', language: str | None = 'ru') -> str:
    """Для бессрочного периода превращает «{period_days} дн.» в «Навсегда», а «на {period_days} дн.» в «навсегда».

    Шаблоны подарков и кнопок периодов пишут единицу измерения прямо в тексте
    («Период: {period_days} дн.»), поэтому подставить «Навсегда» вместо числа нельзя.
    Правится сам шаблон, ключи локалей и вызовы остаются прежними. Если шаблон
    не совпадает с ожидаемым видом (например, текст переопределил админ), он
    возвращается без изменений.
    """
    if not template or not is_lifetime_period(days):
        return template
    label = lifetime_label(language)
    pattern = re.compile(_PREP_RE + r'\{' + re.escape(placeholder) + r'\}\s*' + _UNIT_RE)

    def _repl(match: re.Match) -> str:
        return label.lower() if match.group('prep') and label[:1].isupper() else label

    return pattern.sub(_repl, template)


def for_period_ru(days, *, declined: bool = False) -> str:
    """«на 30 дней» для описаний платежей и операций, для бессрочного периода «навсегда».

    ``declined=True`` склоняет «день/дня/дней» (как format_days_declension),
    иначе пишется «дней», как в прежних описаниях.
    """
    if is_lifetime_period(days):
        return 'навсегда'
    if declined:
        n = int(days)
        if n % 10 == 1 and n % 100 != 11:
            word = 'день'
        elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            word = 'дня'
        else:
            word = 'дней'
        return f'на {n} {word}'
    return f'на {days} дней'
