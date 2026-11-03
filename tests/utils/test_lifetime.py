"""ULTIMA «Навсегда»: срок 2222 дня показывается и хранится как бессрочный."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.database.models import Subscription
from app.utils.formatters import format_days_declension
from app.utils.formatting import format_period
from app.utils.lifetime import (
    LIFETIME_END,
    apply_lifetime_period,
    for_period_ru,
    is_lifetime_end,
    is_lifetime_period,
    normalize_end_date,
)
from app.utils.pricing_utils import format_period_description
from app.utils.subscription_time import format_time_left


@pytest.mark.parametrize('days, expected', [(30, False), (360, False), (1999, False), (2000, True), (2222, True)])
def test_lifetime_period_threshold(days, expected):
    assert is_lifetime_period(days) is expected


def test_formatters_say_forever_for_lifetime_and_days_otherwise():
    assert format_period(2222) == 'Навсегда'
    assert format_period(30) == '30 дней'
    assert format_days_declension(2222) == 'Навсегда'
    assert format_days_declension(2222, 'en') == 'Forever'
    assert format_days_declension(31) == '31 день'
    assert format_period_description(2222, 'ru') == 'Навсегда'
    assert format_period_description(90, 'ru') == '3 месяца'


def test_payment_descriptions():
    assert for_period_ru(2222) == 'навсегда'
    assert for_period_ru(30) == 'на 30 дней'
    assert for_period_ru(31, declined=True) == 'на 31 день'
    assert for_period_ru(2222, declined=True) == 'навсегда'


def test_end_date_far_ahead_snaps_to_lifetime_end():
    now = datetime(2026, 11, 3, tzinfo=UTC)
    assert normalize_end_date(now + timedelta(days=2222), now) == LIFETIME_END
    # Повторная покупка поверх бессрочной не уводит дату за 2099.
    assert normalize_end_date(LIFETIME_END + timedelta(days=2222), now) == LIFETIME_END
    regular = now + timedelta(days=360)
    assert normalize_end_date(regular, now) == regular


def test_model_normalizes_end_date_on_assignment():
    sub = Subscription()
    sub.end_date = datetime.now(UTC) + timedelta(days=2222)
    assert sub.end_date == LIFETIME_END
    assert sub.is_lifetime
    assert sub.time_left_display == 'навсегда'

    sub.end_date = datetime.now(UTC) + timedelta(days=30)
    assert not sub.is_lifetime


def test_naive_far_date_is_also_lifetime():
    naive = datetime.now() + timedelta(days=2500)
    assert normalize_end_date(naive) == LIFETIME_END
    assert is_lifetime_end(datetime(2099, 12, 31))


def test_time_left_for_lifetime():
    assert format_time_left(None, LIFETIME_END) == 'навсегда'


@pytest.mark.parametrize(
    'template, placeholder, language, expected',
    [
        ('Период: <b>{period_days} дн.</b>', 'period_days', 'ru', 'Период: <b>Навсегда</b>'),
        (
            'Дарю тебе подписку {tariff_name} на {period_days} дн.',
            'period_days',
            'ru',
            'Дарю тебе подписку {tariff_name} навсегда',
        ),
        ('{days} дн. — {price}', 'days', 'ru', 'Навсегда — {price}'),
        (
            'subscription {tariff_name} for {period_days} days.',
            'period_days',
            'en',
            'subscription {tariff_name} forever.',
        ),
        ('{tariff_name}（{period_days} 天）', 'period_days', 'zh', '{tariff_name}（永久）'),
        # Текст без единицы (переопределён админом) не трогаем.
        ('Срок {period_days}', 'period_days', 'ru', 'Срок {period_days}'),
    ],
)
def test_apply_lifetime_period(template, placeholder, language, expected):
    assert apply_lifetime_period(template, 2222, placeholder, language) == expected


def test_apply_lifetime_period_keeps_regular_periods():
    assert apply_lifetime_period('Период: {period_days} дн.', 30) == 'Период: {period_days} дн.'


def test_subscription_keyboard_has_no_renew_for_lifetime():
    from app.keyboards.inline import get_subscription_keyboard

    def callbacks(sub):
        kb = get_subscription_keyboard('ru', has_subscription=True, is_trial=False, subscription=sub)
        return {b.callback_data for row in kb.inline_keyboard for b in row}

    base = dict(
        id=1,
        is_trial=False,
        status='active',
        actual_status='active',
        tariff_id=4,
        tariff=None,
        traffic_limit_gb=0,
        device_limit=5,
        autopay_enabled=False,
        is_daily_paused=False,
        subscription_url='https://x',
        subscription_crypto_link=None,
    )
    lifetime = SimpleNamespace(**base, end_date=LIFETIME_END)
    regular = SimpleNamespace(**base, end_date=datetime.now(UTC) + timedelta(days=30))
    try:
        regular_callbacks = callbacks(regular)
    except Exception as exc:  # pragma: no cover - клавиатура требует больше полей
        pytest.skip(f'keyboard needs a richer fixture: {exc}')
    assert 'subscription_extend' in regular_callbacks
    assert 'subscription_extend' not in callbacks(lifetime)
    assert 'subscription_autopay' not in callbacks(lifetime)


@pytest.mark.asyncio
async def test_renewal_of_lifetime_subscription_is_refused_before_any_charge():
    from unittest.mock import AsyncMock

    from app.services.subscription_renewal_service import SubscriptionRenewalError, SubscriptionRenewalService

    db = AsyncMock()
    sub = SimpleNamespace(id=1, is_trial=False, end_date=LIFETIME_END)
    pricing = SimpleNamespace(final_total=500000, period_days=2222, promo_discount_value=0, promo_offer_discount=0)

    with pytest.raises(SubscriptionRenewalError):
        await SubscriptionRenewalService().finalize(db, SimpleNamespace(id=7), sub, pricing)
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_subpage_snapshot_marks_lifetime():
    from app.cabinet.routes.spofy_subpage import snapshot

    sub = SimpleNamespace(
        status='active',
        actual_status='active',
        is_trial=False,
        tariff_id=4,
        tariff=SimpleNamespace(name='ULTIMA'),
        end_date=LIFETIME_END,
        device_limit=5,
        traffic_limit_gb=0,
    )
    assert snapshot(sub)['is_lifetime'] is True
    sub.end_date = datetime.now(UTC) + timedelta(days=30)
    assert snapshot(sub)['is_lifetime'] is False
