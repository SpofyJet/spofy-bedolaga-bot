from app.config import settings


def test_available_languages_default_is_russian_and_english(monkeypatch):
    monkeypatch.setattr(settings, 'AVAILABLE_LANGUAGES', '', raising=False)
    assert settings.get_available_languages() == ['ru', 'en']


def test_available_languages_normalizes_and_deduplicates(monkeypatch):
    monkeypatch.setattr(settings, 'AVAILABLE_LANGUAGES', 'ru,en,EN,en-US', raising=False)
    languages = settings.get_available_languages()
    assert languages[0] == 'ru'
    assert 'en' in languages
    assert 'EN' not in languages
