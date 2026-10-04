"""Скидка «только на один тариф» (ULTIMA): не утекает на другие тарифы и покупки."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.utils.promo_offer import (
    get_user_active_promo_discount_percent,
    offer_discount_source,
    split_discount_source,
)


ULTIMA = 4


def _offer(offer_type='tariff_discount'):
    return SimpleNamespace(notification_type='promo_template_9', extra_data={'offer_type': offer_type})


def _user(source, percent=63):
    return SimpleNamespace(
        promo_offer_discount_percent=percent,
        promo_offer_discount_source=source,
        promo_offer_discount_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_source_carries_the_tariff(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', ULTIMA)
    source = offer_discount_source(_offer())
    assert source == 'tariff:4|promo_template_9'
    assert split_discount_source(source) == (4, 'promo_template_9')


def test_ordinary_offer_source_is_unchanged():
    assert offer_discount_source(_offer('purchase_discount')) == 'promo_template_9'
    assert split_discount_source('promo_template_9') == (None, 'promo_template_9')


def test_discount_only_for_its_tariff():
    user = _user('tariff:4|promo_template_9')
    assert get_user_active_promo_discount_percent(user, ULTIMA) == 63
    assert get_user_active_promo_discount_percent(user, 2) == 0  # другой тариф
    assert get_user_active_promo_discount_percent(user) == 0  # вызов без тарифа: безопасный отказ


def test_ordinary_discount_is_unaffected():
    user = _user('promo_template_3', percent=15)
    assert get_user_active_promo_discount_percent(user) == 15
    assert get_user_active_promo_discount_percent(user, 2) == 15


def test_expired_discount_is_zero():
    user = _user('tariff:4|promo_template_9')
    user.promo_offer_discount_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert get_user_active_promo_discount_percent(user, ULTIMA) == 0
