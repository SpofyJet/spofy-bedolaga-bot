"""Переход между тарифами сравнивает ставки по одному общему периоду, а не по самым коротким периодам."""

from app.database.models import Tariff
from app.services.pricing_engine import pricing_engine


def _tariff(tariff_id, prices):
    return Tariff(
        id=tariff_id,
        name=f't{tariff_id}',
        period_prices={str(k): v for k, v in prices.items()},
        device_limit=3,
        traffic_limit_gb=0,
        allowed_squads=[],
    )


# Реальные цены: у «Стандартного» самый короткий период 14 дней, у «С Обходами» 30.
STANDARD = {14: 11900, 30: 15900, 60: 27900, 90: 35900, 180: 68900, 365: 129000}
BYPASS = {30: 27000, 60: 49500, 90: 72000, 180: 113500, 365: 180000}


def _cost(remaining):
    return pricing_engine.calculate_tariff_switch_cost(_tariff(2, STANDARD), _tariff(3, BYPASS), remaining).upgrade_cost


def test_month_left_costs_the_real_monthly_difference():
    # 270 − 159 = 111 ₽ за месяц; раньше брали ставки 9,0 и 8,5 ₽/день и выходило 15 ₽
    assert _cost(30) == 11100


def test_long_remainder_uses_the_annual_rates():
    # остаток 300 дней: годовые цены, (1800 − 1290) / 365 × 300 ≈ 419 ₽; раньше 150 ₽
    assert _cost(300) == 51000 * 300 // 365
    assert _cost(300) > 40000


def test_cost_is_positive_and_below_the_new_tariff_full_price():
    # Доплата за переход всегда больше нуля, но меньше, чем весь остаток по цене нового тарифа (9 ₽/день).
    for days in (5, 15, 30, 90, 180, 300):
        assert 0 < _cost(days) < 900 * days


def test_cheaper_target_is_free():
    # обратный переход (с обходами на стандарт) ничего не стоит
    result = pricing_engine.calculate_tariff_switch_cost(_tariff(3, BYPASS), _tariff(2, STANDARD), 100)
    assert result.upgrade_cost == 0


def test_without_common_period_falls_back_to_shortest_rates():
    a = _tariff(1, {7: 7000})
    b = _tariff(2, {30: 30000})  # общего периода нет: ставки 10 ₽/день и 10 ₽/день
    assert pricing_engine.calculate_tariff_switch_cost(a, b, 10).upgrade_cost == 0
    c = _tariff(3, {30: 60000})  # 20 ₽/день против 10 ₽/день
    assert pricing_engine.calculate_tariff_switch_cost(a, c, 10).upgrade_cost == 10000
