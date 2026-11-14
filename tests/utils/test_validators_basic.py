"""Базовые тесты для валидаторов из app.utils.validators."""

import pytest

from app.utils import validators


@pytest.mark.parametrize(
    'email,is_valid',
    [
        ('user@example.com', True),
        ('user.name+tag@sub.domain.ru', True),
        ('plain-address', False),
        ('missing-at.example.com', False),
        ('user@invalid', False),
    ],
)
def test_validate_email_handles_expected_patterns(email: str, is_valid: bool) -> None:
    """Проверяем типичные корректные и некорректные адреса."""
    assert validators.validate_email(email) is is_valid


def test_validate_html_tags_rejects_unknown_tags() -> None:
    """Неизвестные HTML теги должны приводить к отказу."""
    ok, message = validators.validate_html_tags('<b>bold</b>')
    assert ok is True
    bad, error = validators.validate_html_tags('<marquee>run</marquee>')
    assert bad is False
    assert 'Неподдерживаемый тег' in error


def test_validate_html_structure_detects_wrong_nesting() -> None:
    """Неправильная вложенность тегов должна сообщаться пользователю."""
    ok, message = validators.validate_html_structure('<b><i>text</i></b>')
    assert ok is True
    bad, error = validators.validate_html_structure('<b><i>text</b></i>')
    assert bad is False
    assert 'Неправильная вложенность' in error
