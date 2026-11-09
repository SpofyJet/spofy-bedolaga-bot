"""Regression tests for Telegram bug report #602326.

«Скидки от промогруппы не отображаются в докупке трафика» — promo-group
discounts were never shown in the cabinet's "buy traffic" sheet.

Root cause: ``GET /subscription/traffic-packages`` returned raw base prices
with no discount fields, even though ``POST /subscription/traffic`` charged the
discounted amount and the frontend ``TrafficTopupSheet`` already rendered
``discount_percent`` / ``base_price_kopeks``. The endpoint now mirrors the
device/renewal endpoints and applies the promo-group traffic discount so the
sheet can display the strike-through original price and the ``-N%`` badge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cabinet.routes.subscription_modules import traffic as traffic_route
from app.database.models import PromoGroup, Subscription, User


def _make_user(*, traffic_discount_percent: int, apply_to_addons: bool = True) -> User:
    pg = PromoGroup(
        name='Test promo group',
        traffic_discount_percent=traffic_discount_percent,
        server_discount_percent=0,
        device_discount_percent=0,
        apply_discounts_to_addons=apply_to_addons,
        is_default=False,
    )
    user = User(id=1, telegram_id=123, balance_kopeks=1_000_000)
    # Eager-loaded relationships (mirrors get_user_by_id): primary promo group
    # resolves via user_promo_groups first, falling back to .promo_group.
    user.promo_group = pg
    user.user_promo_groups = []
    return user


def _make_subscription() -> Subscription:
    sub = Subscription(
        id=10,
        user_id=1,
        status='active',
        is_trial=False,
        traffic_limit_gb=200,
        tariff_id=5,
    )
    sub.end_date = datetime.now(UTC) + timedelta(days=30)
    return sub


@pytest.fixture
def tariff_packages(monkeypatch):
    """A subscription on a tariff with two traffic packages."""
    tariff = SimpleNamespace(
        traffic_topup_enabled=True,
        traffic_limit_gb=100,
        get_traffic_topup_packages=lambda: {50: 10000, 100: 18000},
    )
    monkeypatch.setattr('app.database.crud.tariff.get_tariff_by_id', AsyncMock(return_value=tariff))

    async def _fake_resolve(db, user, subscription_id):
        return _make_subscription()

    monkeypatch.setattr(traffic_route, 'resolve_subscription', _fake_resolve)


@pytest.mark.asyncio
async def test_traffic_packages_expose_promo_group_discount(tariff_packages):
    """A 20% traffic promo-group discount surfaces on every package."""
    user = _make_user(traffic_discount_percent=20)

    result = await traffic_route.get_traffic_packages(user=user, db=object(), subscription_id=None)

    assert len(result) == 2

    pkg50 = next(p for p in result if p.gb == 50)
    assert pkg50.discount_percent == 20
    assert pkg50.base_price_kopeks == 10000  # original (struck through in UI)
    assert pkg50.price_kopeks == 8000  # discounted price shown to the user
    assert pkg50.price_rubles == pytest.approx(80.0)

    pkg100 = next(p for p in result if p.gb == 100)
    assert pkg100.discount_percent == 20
    assert pkg100.base_price_kopeks == 18000
    assert pkg100.price_kopeks == 14400


@pytest.mark.asyncio
async def test_traffic_packages_no_discount_when_group_has_none(tariff_packages):
    """No promo discount → no discount fields, raw price unchanged."""
    user = _make_user(traffic_discount_percent=0)

    result = await traffic_route.get_traffic_packages(user=user, db=object(), subscription_id=None)

    pkg50 = next(p for p in result if p.gb == 50)
    assert pkg50.discount_percent == 0
    assert pkg50.base_price_kopeks is None  # no strike-through when nothing is discounted
    assert pkg50.price_kopeks == 10000


@pytest.mark.asyncio
async def test_traffic_packages_respect_apply_discounts_to_addons_flag(tariff_packages):
    """When the promo group opts out of addon discounts, traffic stays full price."""
    user = _make_user(traffic_discount_percent=30, apply_to_addons=False)

    result = await traffic_route.get_traffic_packages(user=user, db=object(), subscription_id=None)

    pkg50 = next(p for p in result if p.gb == 50)
    assert pkg50.discount_percent == 0
    assert pkg50.base_price_kopeks is None
    assert pkg50.price_kopeks == 10000


@pytest.mark.asyncio
async def test_traffic_packages_apply_discount_in_tariff_mode(monkeypatch):
    """Tariff-mode packages go through the same discount path as classic mode."""
    type(traffic_route.settings)

    class _FakeTariff:
        traffic_topup_enabled = True
        traffic_limit_gb = 200

        def get_traffic_topup_packages(self):
            return {50: 10000, 100: 18000}

    async def _fake_get_tariff(db, tariff_id):
        return _FakeTariff()

    import app.database.crud.tariff as tariff_crud

    monkeypatch.setattr(tariff_crud, 'get_tariff_by_id', _fake_get_tariff)

    sub = _make_subscription()
    sub.tariff_id = 5

    async def _fake_resolve(db, user, subscription_id):
        return sub

    monkeypatch.setattr(traffic_route, 'resolve_subscription', _fake_resolve)

    user = _make_user(traffic_discount_percent=25)

    result = await traffic_route.get_traffic_packages(user=user, db=object(), subscription_id=None)

    pkg50 = next(p for p in result if p.gb == 50)
    assert pkg50.discount_percent == 25
    assert pkg50.base_price_kopeks == 10000
    assert pkg50.price_kopeks == 7500  # 25% off
