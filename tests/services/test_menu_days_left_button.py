"""Кнопка «⏳ Осталось N — продлить» в главном меню: появляется к концу подписки и красиво склоняет срок."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.keyboards.inline import _days_left_button
from app.localization.texts import get_texts


def _sub(remaining: timedelta, *, is_trial=False, sub_id=5):
    return SimpleNamespace(id=sub_id, is_trial=is_trial, end_date=datetime.now(UTC) + remaining)


def _button(remaining, **kw):
    return _days_left_button(_sub(remaining, **kw), get_texts('ru'), 'ru')


@pytest.mark.parametrize(
    ('remaining', 'expected'),
    [
        (timedelta(days=3, hours=2), '⏳ Осталось 3 дня — продлить'),
        (timedelta(days=1, hours=2), '⏳ Осталось 1 день — продлить'),
        (timedelta(days=6, hours=5), '⏳ Осталось 6 дней — продлить'),
        (timedelta(hours=5, minutes=10), '⏳ Осталось 6 ч — продлить'),  # меньше суток: часы, округление вверх
    ],
)
def test_paid_renew_button_text(remaining, expected):
    button = _button(remaining)
    assert button.text == expected
    assert button.callback_data == 'subscription_extend'
    assert button.style == 'primary'  # синяя


def test_far_from_the_end_has_no_button():
    assert _button(timedelta(days=8)) is None
    assert _button(timedelta(days=2222)) is None  # ULTIMA «навсегда»
    assert _button(timedelta(days=7, hours=1)) is None


def test_expired_has_no_button():
    assert _button(timedelta(hours=-1)) is None


def test_trial_has_no_countdown_button():
    # У триала в меню остаётся обычная «Купить подписку»: отсчёта дней нет ни за сутки, ни за час.
    assert _button(timedelta(days=1, hours=3), is_trial=True) is None
    assert _button(timedelta(hours=3), is_trial=True) is None


def test_no_subscription_no_button():
    assert _days_left_button(None, get_texts('ru'), 'ru') is None
