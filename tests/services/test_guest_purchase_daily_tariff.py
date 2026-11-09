"""Regression tests for daily-tariff pricing on landing/guest purchases.

Background — the bug (Telegram report #543696)
----------------------------------------------
Landing pages that sold a *daily* tariff (``is_daily=True``) showed a price
of 0 and could not be purchased. Daily tariffs keep their price in
``daily_price_kopeks`` and leave ``period_prices`` empty, but the landing
config loader and the guest-purchase validator only ever read
``period_prices`` (via ``get_price_for_period`` / ``get_available_periods``).
For a daily tariff that meant "no period, no price" → the tariff was dropped
or surfaced at price 0.

The fix routes both paths through the daily-aware model helpers
``Tariff.get_purchasable_periods`` / ``Tariff.get_purchasable_price_for_period``,
which treat a daily tariff as a single purchasable period of 1 day priced at
``daily_price_kopeks``. These tests pin that behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace


def _daily_tariff(tariff_id: int = 1, daily_price_kopeks: int = 5000) -> SimpleNamespace:
    """A stub daily tariff mirroring the real model's daily-aware helpers."""

    def get_price_for_period(days: int) -> int | None:
        return None  # daily tariffs keep no period_prices

    def get_available_periods() -> list[int]:
        return []

    def get_purchasable_periods() -> list[int]:
        return [1] if daily_price_kopeks else []

    def get_purchasable_price_for_period(days: int) -> int | None:
        if days == 1:
            return daily_price_kopeks or None
        return None

    return SimpleNamespace(
        id=tariff_id,
        is_active=True,
        is_daily=True,
        daily_price_kopeks=daily_price_kopeks,
        get_price_for_period=get_price_for_period,
        get_available_periods=get_available_periods,
        get_purchasable_periods=get_purchasable_periods,
        get_purchasable_price_for_period=get_purchasable_price_for_period,
    )
