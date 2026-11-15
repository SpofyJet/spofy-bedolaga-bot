"""Смена тарифа админом сохраняет докупленные устройства.

Админ меняет тариф в кабинете (одному пользователю) и в админке бота. Это
смена метки, а не покупка — денег не списывается, докупленные устройства уже
оплачены до конца срока. Админка бота так и делала (лимит = база нового тарифа
+ докупки сверх базы старого), а кабинет звал calc_device_limit_on_tariff_switch,
которая с aec01ce0 сбрасывает лимит до базы нового тарифа: после смены тарифа
пользователи теряли оплаченные устройства, хотя комментарий над вызовом
обещал «Preserve extra purchased devices». Смена тарифа самим пользователем
по-прежнему сбрасывает лимит — там считается цена перехода.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.database.crud.subscription import (
    calc_device_limit_on_admin_tariff_change,
    calc_device_limit_on_tariff_switch,
)


@pytest.fixture(autouse=True)
def no_global_cap(monkeypatch):
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)


@pytest.mark.parametrize(
    'current, old_base, new_base, max_limit, expected',
    [
        # Докупки сверх базы старого тарифа переезжают на базу нового.
        (11, 8, 8, None, 11),
        (3, 1, 1, None, 3),
        (3, 1, 2, None, 4),
        # Докупок не было — лимит равен базе нового тарифа, в том числе ниже прежнего.
        (8, 8, 1, None, 1),
        # База старого неизвестна — переносить нечего.
        (5, None, 2, None, 2),
        # Лимит без ограничения (0 / пусто) — докупок нет.
        (0, 8, 2, None, 2),
        (None, 8, 2, None, 2),
        # Потолок тарифа.
        (11, 8, 8, 10, 10),
        # Новый тариф безлимитный (база 0) — лимит остаётся безлимитным.
        (11, 8, 0, None, 0),
        (5, 1, 0, 2, 0),
    ],
)
def test_admin_change_carries_extra_devices(current, old_base, new_base, max_limit, expected):
    assert calc_device_limit_on_admin_tariff_change(current, old_base, new_base, max_limit) == expected


def test_global_cap_applies_without_tariff_cap(monkeypatch):
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 9)

    assert calc_device_limit_on_admin_tariff_change(11, 8, 8, None) == 9


def test_user_switch_keeps_paid_devices_in_spofy():
    # Spofy: смена тарифа самим пользователем тоже переносит докупленные места
    # (upstream aec01ce0 сбрасывает до базы — у нас сознательно иначе).
    assert calc_device_limit_on_tariff_switch(11, 8, 8, None) == 11
