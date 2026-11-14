import math
from datetime import UTC, datetime

import structlog


logger = structlog.get_logger(__name__)


def calculate_months_from_days(days: int) -> int:
    return max(1, round(days / 30))


def calculate_period_device_cost(monthly_price: int, extra_devices: int, period_days: int) -> int:
    """Cost in kopeks for a periodic tariff's devices; one priced month is 30 days."""
    return max(0, monthly_price) * max(0, extra_devices) * max(0, period_days) // 30


def calculate_price_per_month(price_kopeks: int, period_days: int) -> int:
    """Месячная ставка для периода длиной period_days дней (месяц = 30 дней).

    Считается пропорцией, а не делением на округлённое число месяцев:
    для коротких (7 дней) и некратных 30 (45 дней) периодов делитель
    зажимался в 1-2 месяца, и цена периода уходила в отображение как
    месячная. Значение только для показа, начисления идут по полной
    цене периода.
    """
    if price_kopeks <= 0 or period_days <= 0:
        return max(0, price_kopeks)
    return round(price_kopeks * 30 / period_days)


def calculate_prorated_price(monthly_price: int, end_date: datetime, min_charge_days: int = 1) -> tuple[int, int]:
    """Calculate prorated price based on remaining days.

    Returns:
        tuple of (total_price_kopeks, days_charged)
    """
    now = datetime.now(UTC)
    days_remaining = max(1, math.ceil((end_date - now).total_seconds() / 86400))
    days_to_charge = max(min_charge_days, days_remaining)

    total_price = monthly_price * days_to_charge // 30
    if monthly_price > 0:
        total_price = max(100, total_price)  # Минимум 1 рубль

    logger.debug(
        'Расчет пропорциональной цены',
        monthly_price=monthly_price / 100,
        days_to_charge=days_to_charge,
        total_price=total_price / 100,
    )

    return total_price, days_to_charge


def count_chargeable_devices(devices_to_add: int, current_devices: int, included_devices: int) -> int:
    """Сколько докупаемых устройств платные: места в пределах тарифа бесплатны."""
    free_devices = max(0, included_devices - current_devices)
    return max(0, devices_to_add - free_devices)


def calculate_device_addon_price(
    device_price_kopeks: int,
    chargeable_devices: int,
    days_left: int,
    *,
    flat: bool,
    discount_percent: int = 0,
) -> int:
    """Цена докупки устройств — та же, что показывает кабинет.

    ``flat`` — тариф с разовой ценой устройства (``Tariff.device_price_flat``): цена не
    зависит от остатка дней. Без этого подписка до 2099 года стоила бы как 26 тысяч дней.
    """
    if chargeable_devices <= 0:
        return 0

    base_price = device_price_kopeks * chargeable_devices
    if not flat:
        base_price = int(base_price * days_left / 30)
    base_price = max(100, base_price)  # Минимум 1 рубль

    if discount_percent <= 0:
        return base_price
    discounted_price, _ = apply_percentage_discount(base_price, discount_percent)
    return discounted_price if discount_percent >= 100 else max(100, discounted_price)


def apply_percentage_discount(amount: int, percent: int) -> tuple[int, int]:
    """Apply percentage discount using PricingEngine's floor division.

    Returns (discounted_amount, discount_value).
    """
    from app.services.pricing_engine import PricingEngine

    if amount <= 0 or percent <= 0:
        return amount, 0

    discounted = PricingEngine.apply_discount(amount, percent)
    return discounted, amount - discounted


def _pluralize_days_ru(n: int) -> str:
    """Склонение слова 'день' по числу: 1 день, 2 дня, 5 дней."""
    mod100 = n % 100
    mod10 = n % 10
    if 11 <= mod100 <= 19:
        return 'дней'
    if mod10 == 1:
        return 'день'
    if 2 <= mod10 <= 4:
        return 'дня'
    return 'дней'


def format_period_description(days: int, language: str = 'ru') -> str:
    from app.utils.lifetime import is_lifetime_period, lifetime_label

    if is_lifetime_period(days):
        return lifetime_label(language)
    language_code = (language or 'ru').split('-')[0].lower()
    if language_code == 'ru':
        if days == 30:
            return '1 месяц'
        if days == 60:
            return '2 месяца'
        if days == 90:
            return '3 месяца'
        if days == 180:
            return '6 месяцев'
        if days == 360:
            return '12 месяцев'
        return f'{days} {_pluralize_days_ru(days)}'

    if days == 30:
        return '1 month'
    if days == 60:
        return '2 months'
    if days == 90:
        return '3 months'
    if days == 180:
        return '6 months'
    if days == 360:
        return '12 months'
    day_word = 'day' if days == 1 else 'days'
    return f'{days} {day_word}'


def validate_pricing_calculation(base_price: int, monthly_additions: int, months: int, total_calculated: int) -> bool:
    expected_total = base_price + (monthly_additions * months)
    is_valid = expected_total == total_calculated

    if not is_valid:
        logger.warning(
            'Несоответствие в расчете цены: ожидаемая и фактическая сумма не совпадают',
            expected_total=expected_total / 100,
            total_calculated=total_calculated / 100,
        )
        logger.warning(
            'Детали расчета цены: базовая цена, месячные дополнения и число месяцев',
            base_price=base_price / 100,
            monthly_additions=monthly_additions / 100,
            months=months,
        )

    return is_valid
