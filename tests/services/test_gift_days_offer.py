from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.handlers.subscription import tariff_purchase as tp
from app.localization.texts import get_texts
from app.services.gift_days_offer import (
    PeriodGift,
    human_date,
    months_text,
    purchased_days,
)


@pytest.mark.parametrize(
    ('description', 'days'),
    [
        ('Покупка тарифа ⭐️ Стандартный на 90 дней', 90),
        ('Продление тарифа 🏴‍☠️ С Обходами на 180 дней', 180),
        ("Покупка тарифа '⭐️ Стандартный' на 365 дней (промо -20%)", 365),
        ('Продление подписки на 90 дней (⭐️ Стандартный)', 90),
        ('Автопродление истёкшей подписки на 30 дней', 30),
        ('Покупка тарифа 👑 ULTIMA на 1 дня', 1),
        ('Покупка тарифа ⭐️ Стандартный на 90 дней · 🔗 СТРАНИЦА ПОДПИСКИ', 90),
        ('Покупка тарифа 👑 ULTIMA навсегда', None),
        ('Покупка 1 доп. устройств', None),
        ('Изменение устройств с 3 до 4 за 90 дн.', None),
        ("Переход на тариф '🏴‍☠️ С Обходами' (доплата за 90 дней)", None),
        ('Переключение на тариф 🏴‍☠️ С Обходами', None),
        ('Докупка 50 ГБ трафика', None),
        (None, None),
    ],
)
def test_purchased_days_reads_every_purchase_format(description, days):
    assert purchased_days(description) == days


def test_gift_applies_from_three_months_and_never_to_lifetime():
    gift = PeriodGift(offer_id=1, min_days=90, bonus_days=90, expires_at=datetime.now(UTC))
    assert [gift.days_for(d) for d in (14, 30, 60, 89, 90, 180, 365, 36500, None)] == [0, 0, 0, 0, 90, 90, 90, 0, 0]


def test_months_text():
    assert months_text(90) == '3 месяца'
    assert months_text(30) == '1 месяц'
    assert months_text(150) == '5 месяцев'
    assert months_text(330) == '11 месяцев'
    assert months_text(90, short=True) == '3 мес.'
    assert months_text(10) == '10 дн.'


def test_human_date_adds_year_only_when_it_differs():
    now = datetime(2026, 11, 21, 12, tzinfo=UTC)
    assert human_date(datetime(2026, 11, 28, 12, tzinfo=UTC), now=now) == '28 ноября'
    assert human_date(datetime(2027, 5, 21, 12, tzinfo=UTC), now=now) == '21 мая 2027'


def _tariff():
    return SimpleNamespace(
        id=1,
        name='Стандартный',
        period_prices={'30': 17900, '90': 40900, '365': 149000},
        highlight_period_days=90,
        device_limit=3,
        device_price_kopeks=0,
    )


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_period_buttons_show_gift_only_on_eligible_periods():
    gift = PeriodGift(offer_id=1, min_days=90, bonus_days=90, expires_at=datetime.now(UTC) + timedelta(days=7))
    labels = _labels(tp.get_tariff_periods_keyboard(_tariff(), 'ru', gift=gift))
    gifted = [label for label in labels if 'в подарок' in label]
    assert len(gifted) == 2
    assert all(label.startswith('🎁 ') and '+3 мес. в подарок' in label for label in gifted)
    assert any(label.startswith('30 дней') for label in labels)
    assert not any('в подарок' in label for label in _labels(tp.get_tariff_periods_keyboard(_tariff(), 'ru')))


def test_extend_buttons_show_gift():
    gift = PeriodGift(offer_id=1, min_days=90, bonus_days=90, expires_at=datetime.now(UTC) + timedelta(days=7))
    labels = _labels(
        tp.get_tariff_extend_keyboard(_tariff(), 'ru', subscription_device_limit=3, subscription_id=5, gift=gift)
    )
    assert sum('+3 мес. в подарок' in label for label in labels) == 2


def test_confirm_period_and_note():
    texts = get_texts('ru')
    gift = PeriodGift(offer_id=1, min_days=90, bonus_days=90, expires_at=datetime(2026, 11, 28, 20, tzinfo=UTC))
    assert tp._period_with_gift(texts, 90, gift) == '90 дней + 3 месяца в подарок 🎁'
    assert tp._period_with_gift(texts, 30, gift) == '30 дней'
    assert tp._period_with_gift(texts, 90, None) == '90 дней'
    note = tp._gift_note(texts, gift, 'ru')
    assert 'от 3 мес.' in note and '3 месяца бесплатно' in note and 'ноября' in note
    assert tp._gift_note(texts, None, 'ru') == ''


async def test_gift_lookup_failure_never_breaks_purchase_screen():
    from app.services.gift_days_offer import active_gift

    class Broken:
        def begin_nested(self):
            raise RuntimeError('db down')

    assert await active_gift(Broken(), 1) is None
    assert await active_gift(Broken(), None) is None
