"""«Подключить за минуту»: первый экран нового человека, цена месяца на длинных сроках."""

from types import SimpleNamespace

from app.config import settings
from app.handlers import menu
from app.handlers.subscription.tariff_purchase import _period_button_text
from app.localization.texts import get_texts


def _user(subs=(), used=False):
    return SimpleNamespace(subscriptions=list(subs), is_trial_already_used=lambda: used, auth_type='telegram')


def test_new_user_sees_one_thought_and_trial(monkeypatch):
    monkeypatch.setattr(settings, 'TRIAL_DURATION_DAYS', 2)
    monkeypatch.setattr(settings, 'TRIAL_DISABLED_FOR', 'none')
    assert menu.is_new_user_with_free_trial(_user())
    text = menu._new_user_menu_text(get_texts('ru'))
    assert '2 дня бесплатно' in text
    assert 'Выберите действие' not in text


def _tariff():
    return SimpleNamespace(highlight_period_days=None)


def test_per_month_price_on_long_periods():
    texts = get_texts('ru')
    prices = {'30': 15900, '90': 35900, '365': 129000}
    assert _period_button_text(_tariff(), 30, 15900, '159 ₽', prices, texts) == '📅 30 дней — 159 ₽'
    assert '359 ₽ · 120 ₽/мес' in _period_button_text(_tariff(), 90, 35900, '359 ₽', prices, texts)
    # 365 дней = 12 месяцев, 107,5 ₽ округляем вверх
    assert '1 290 ₽ · 108 ₽/мес' in _period_button_text(_tariff(), 365, 129000, '1 290 ₽', prices, texts)
