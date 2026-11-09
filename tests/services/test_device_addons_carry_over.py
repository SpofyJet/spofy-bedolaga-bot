"""Spofy: докупленные места переносятся, только если на новом тарифе место не дороже."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.crud.subscription import (
    calc_device_limit_on_admin_tariff_change,
    calc_device_limit_on_tariff_switch,
    device_addons_carry_over,
)


STANDARD = SimpleNamespace(device_limit=3, device_price_kopeks=5000, device_price_flat=False, max_device_limit=None)
BYPASS = SimpleNamespace(device_limit=3, device_price_kopeks=5000, device_price_flat=False, max_device_limit=None)
ULTIMA = SimpleNamespace(device_limit=5, device_price_kopeks=100000, device_price_flat=True, max_device_limit=None)


def _switch(calc, current, old, new):
    return calc(
        current_device_limit=current,
        old_tariff_device_limit=old.device_limit,
        new_tariff_device_limit=new.device_limit,
        max_device_limit=new.max_device_limit,
        old_tariff=old,
        new_tariff=new,
    )


@pytest.mark.parametrize('calc', [calc_device_limit_on_tariff_switch, calc_device_limit_on_admin_tariff_change])
def test_monthly_devices_do_not_move_to_ultima(calc):
    # Стандартный 3 + 2 докупленных по 50 ₽/мес → ULTIMA: только база 5.
    assert _switch(calc, 5, STANDARD, ULTIMA) == 5


@pytest.mark.parametrize('calc', [calc_device_limit_on_tariff_switch, calc_device_limit_on_admin_tariff_change])
def test_ultima_devices_move_down(calc):
    # ULTIMA 5 + 2 места по 1000 ₽ → Стандартный: база 3 + 2.
    assert _switch(calc, 7, ULTIMA, STANDARD) == 5


@pytest.mark.parametrize('calc', [calc_device_limit_on_tariff_switch, calc_device_limit_on_admin_tariff_change])
def test_same_device_price_moves(calc):
    assert _switch(calc, 6, STANDARD, BYPASS) == 6
    assert _switch(calc, 6, BYPASS, STANDARD) == 6


def test_rule_matrix():
    assert device_addons_carry_over(STANDARD, ULTIMA) is False
    assert device_addons_carry_over(ULTIMA, STANDARD) is True
    assert device_addons_carry_over(STANDARD, BYPASS) is True
    cheaper = SimpleNamespace(device_price_kopeks=3000, device_price_flat=False)
    assert device_addons_carry_over(cheaper, STANDARD) is False  # место подорожало
    assert device_addons_carry_over(STANDARD, cheaper) is True
    assert device_addons_carry_over(None, ULTIMA) is True  # сравнить не с чем — не отбираем
    no_sale = SimpleNamespace(device_price_kopeks=None, device_price_flat=False)
    assert device_addons_carry_over(no_sale, STANDARD) is True


def test_unlimited_new_base_stays_unlimited():
    unlimited = SimpleNamespace(
        device_limit=0, device_price_kopeks=None, device_price_flat=False, max_device_limit=None
    )
    assert _switch(calc_device_limit_on_tariff_switch, 6, STANDARD, unlimited) == 0


def test_every_call_site_passes_tariffs():
    """Без old_tariff/new_tariff правило молча не применится — следим за всеми вызовами."""
    root = Path(__file__).resolve().parents[2] / 'app'
    pattern = re.compile(
        r'(calc_device_limit_on_tariff_switch|calc_device_limit_on_admin_tariff_change|_calc_sw_devices)\('
    )
    offenders = []
    for path in root.rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        for match in pattern.finditer(source):
            if source[max(0, match.start() - 4) : match.start()] == 'def ':
                continue
            depth, end = 1, match.end()
            while depth:
                depth += {'(': 1, ')': -1}.get(source[end], 0)
                end += 1
            call = source[match.end() : end]
            if 'new_tariff=' not in call or 'old_tariff=' not in call:
                offenders.append(f'{path.relative_to(root)}:{source[: match.start()].count(chr(10)) + 1}')
    assert offenders == []
