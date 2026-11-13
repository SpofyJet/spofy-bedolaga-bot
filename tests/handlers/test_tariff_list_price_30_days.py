"""Список тарифов: цена за 30 дней, а не «от» самого короткого периода.

«от 159₽» у «Стандартного» — цена 14 дней; рядом «С Обходами» с «от 310₽» за 30 дней. Сравнить
тарифы по списку было нельзя: 150 из 441 новичков за 30 дней возвращались со списка периодов.
"""

from types import SimpleNamespace

import pytest

from app.config import settings
from app.handlers.subscription import tariff_purchase as m


def _tariff(tariff_id: int, name: str, period_prices: dict, **extra):
    return SimpleNamespace(
        id=tariff_id,
        name=name,
        period_prices=period_prices,
        traffic_limit_gb=0,
        device_limit=3,
        description=None,
        is_daily=False,
        daily_price_kopeks=0,
        allowed_squads=[],
        **extra,
    )


STANDARD = _tariff(2, 'Стандартный', {'14': 15900, '30': 17900, '60': 31900, '365': 149000})
BYPASS = _tariff(3, 'С Обходами', {'30': 31000, '60': 57000})
ULTIMA = _tariff(4, 'ULTIMA', {'2222': 579000})


@pytest.fixture(autouse=True)
def _no_bypass_squad(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', '', raising=False)


def _line(text: str, name: str) -> str:
    return next(line for line in text.split('\n') if name in line)


def test_list_shows_the_30_day_price_not_the_shortest_period():
    text = m.format_tariffs_list_text([STANDARD, BYPASS])

    assert _line(text, 'Стандартный').endswith('179 ₽ за 30 дней')
    assert _line(text, 'С Обходами').endswith('310 ₽ за 30 дней')
    assert '159' not in text, 'цена 14 дней в списке больше не показывается'
    assert 'от ' not in text


def test_integer_period_keys_are_found_too():
    text = m.format_tariffs_list_text([_tariff(5, 'Месячный', {14: 15900, 30: 17900})])

    assert _line(text, 'Месячный').endswith('179 ₽ за 30 дней')


def test_tariff_without_a_30_day_period_keeps_the_old_wording():
    text = m.format_tariffs_list_text([ULTIMA])

    assert _line(text, 'ULTIMA').endswith('от 5790₽')
    assert 'за 30 дней' not in text


def test_discount_is_taken_for_the_30_day_period_and_keeps_its_icon(monkeypatch):
    asked: list[int] = []

    def discount(db_user, period_days, tariff_id=None):
        asked.append(period_days)
        return (20, 0, 20) if period_days == 30 else (0, 0, 0)

    monkeypatch.setattr(m, '_get_user_period_discount', discount)

    text = m.format_tariffs_list_text([STANDARD], db_user=SimpleNamespace(language='ru'))

    assert asked == [30]
    assert _line(text, 'Стандартный').endswith('143.20 ₽🔥 за 30 дней'), 'та же запись цены, что на кнопках периодов'
