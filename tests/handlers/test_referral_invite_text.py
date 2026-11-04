"""The invite a user forwards to a friend is plain text: no raw <tg-emoji> tags, whole words for days."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.config import settings
from app.handlers import referral
from app.localization.texts import get_texts


@pytest.fixture(autouse=True)
def _trial(monkeypatch):
    monkeypatch.setattr(settings, 'TRIAL_DURATION_DAYS', 2)
    monkeypatch.setattr(settings, 'TRIAL_DISABLED_FOR', 'none')
    monkeypatch.setattr(type(settings), 'is_trial_paid_activation_enabled', lambda self: False)
    monkeypatch.setattr(type(settings), 'is_referral_levels_scheme', lambda self: False)
    monkeypatch.setattr(settings, 'REFERRAL_FIRST_TOPUP_BONUS_KOPEKS', 0)


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_share_text_has_no_markup(lang):
    url = referral._build_referral_share_url('https://t.me/bot?start=ref_x', get_texts(lang))
    text = parse_qs(urlparse(url).query)['text'][0]
    assert '<' not in text and 'tg-emoji' not in text
    assert 'дн.' not in text


def test_russian_share_text_reads_naturally():
    url = referral._build_referral_share_url('https://t.me/bot?start=ref_x', get_texts('ru'))
    text = parse_qs(urlparse(url).query)['text'][0]
    assert text == (
        'Привет! Пользуюсь Spofy VPN — советую и тебе.\n\n'
        '🎁 2 дня бесплатно — без карты.\n'
        '🤝 По моей ссылке — ещё 2 дня в подарок, когда подключишься.'
    )


@pytest.mark.parametrize(
    ('days', 'lang', 'phrase'),
    [
        (1, 'ru', '1 день'),
        (2, 'ru', '2 дня'),
        (5, 'ru', '5 дней'),
        (11, 'ru', '11 дней'),
        (2, 'ua', '2 дні'),
        (1, 'en', '1 day'),
    ],
)
def test_days_phrase(days, lang, phrase):
    assert referral._days_phrase(days, lang) == phrase
