"""Тесты для базовых форматтеров из app.utils.formatters."""

from datetime import UTC, datetime, timedelta

from app.utils import formatters
from tests.fixtures.local_day import (  # noqa: F401
    reset_local_timezone_cache,
    use_timezone,
)


def test_format_datetime_handles_iso_strings(fixed_datetime: datetime, monkeypatch) -> None:
    """ISO-строка должна корректно преобразовываться в отформатированный текст.

    Вывод идёт в часовом поясе оператора (settings.TIMEZONE) — фиксируем UTC.
    """
    use_timezone(monkeypatch, 'UTC')
    iso_value = fixed_datetime.isoformat()
    assert formatters.format_datetime(iso_value) == fixed_datetime.strftime('%d.%m.%Y %H:%M')


def test_format_time_ago_returns_human_readable_text() -> None:
    """Разница во времени должна переводиться в человеко-понятную строку."""
    point_in_time = datetime.now(UTC) - timedelta(minutes=5)
    assert formatters.format_time_ago(point_in_time, language='ru') == '5 мин. назад'
    assert formatters.format_time_ago(point_in_time, language='en') == '5 minutes ago'


def test_format_days_declension_handles_russian_rules() -> None:
    """Склонение дней в русском языке зависит от числа."""
    assert formatters.format_days_declension(1) == '1 день'
    assert formatters.format_days_declension(3) == '3 дня'
    assert formatters.format_days_declension(10) == '10 дней'


def test_format_username_link_wraps_telegram_handle_in_anchor() -> None:
    """Rich-сообщения идут со skip_entity_detection=True — ссылка нужна явная."""
    assert formatters.format_username_link('durov') == '<a href="https://t.me/durov">@durov</a>'


def test_format_username_link_does_not_double_the_at_sign() -> None:
    """Логин может прийти уже с собакой — в тексте она должна остаться одна."""
    assert formatters.format_username_link('@durov') == '<a href="https://t.me/durov">@durov</a>'


def test_format_username_link_returns_fallback_without_username() -> None:
    """Пустой логин отдаётся текстом-заглушкой, без собаки и без ссылки."""
    assert formatters.format_username_link(None, 'отсутствует') == 'отсутствует'
    assert formatters.format_username_link('', 'отсутствует') == 'отсутствует'
    assert formatters.format_username_link('@', 'отсутствует') == 'отсутствует'
    assert formatters.format_username_link(None) == ''


def test_format_username_link_keeps_non_telegram_logins_as_text() -> None:
    """OAuth-регистрация кладёт в users.username логин Discord/Яндекса.

    Он живёт в чужом пространстве имён: t.me/<логин> ведёт либо в никуда, либо на
    постороннего человека, поэтому ссылку на такое значение ставить нельзя.
    """
    assert formatters.format_username_link('ivan.petrov') == '@ivan.petrov'
    assert formatters.format_username_link('ab') == '@ab'
    assert formatters.format_username_link('5abcd') == '@5abcd'
    assert formatters.format_username_link('a' * 33) == '@' + 'a' * 33


def test_format_username_link_escapes_html_metacharacters() -> None:
    """Значение попадает и в href, и в текст — экранируем оба."""
    assert formatters.format_username_link('bo&b') == '@bo&amp;b'
    assert formatters.format_username_link('<b>x</b>') == '@&lt;b&gt;x&lt;/b&gt;'


def test_admin_dates_are_shown_in_operator_zone(monkeypatch, reset_local_timezone_cache) -> None:
    """Жалоба 4.12.0: панель и «Моя подписка» — 18.09.2026 14:17, админка бота — 11:17 (UTC)."""
    use_timezone(monkeypatch, 'Europe/Moscow')
    end_date = datetime(2026, 9, 18, 11, 17, tzinfo=UTC)

    assert formatters.format_datetime(end_date) == '18.09.2026 14:17'
    assert formatters.format_datetime(end_date.replace(tzinfo=None)) == '18.09.2026 14:17'
    assert formatters.format_datetime('2026-09-18T11:17:00Z') == '18.09.2026 14:17'
