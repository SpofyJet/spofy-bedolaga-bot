"""Тесты канонизации почтовых адресов из app.utils.email_alias.

Проверка «email занят» сравнивала адреса с точностью до регистра, поэтому
`user+1@gmail.com` и `u.ser@gmail.com` заводили отдельные аккаунты, хотя письма
идут в один ящик — и каждый такой аккаунт получал свою пробную подписку.
"""

import pytest

from app.utils.email_alias import (
    canonical_email,
)


class TestCanonicalEmail:
    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [
            ('User@Gmail.com', 'user@gmail.com'),
            ('  user@gmail.com  ', 'user@gmail.com'),
            ('user+vpn@gmail.com', 'user@gmail.com'),
            ('user+a+b@gmail.com', 'user@gmail.com'),
            ('u.s.e.r@gmail.com', 'user@gmail.com'),
            ('u.s.e.r+tag@gmail.com', 'user@gmail.com'),
            ('user@googlemail.com', 'user@gmail.com'),
            ('user+tag@yandex.ru', 'user@yandex.ru'),
            ('user@ya.ru', 'user@yandex.ru'),
            ('user@yandex.com', 'user@yandex.ru'),
            ('user+tag@outlook.com', 'user@outlook.com'),
        ],
    )
    def test_aliases_collapse_to_one_mailbox(self, raw: str, expected: str) -> None:
        assert canonical_email(raw) == expected

    def test_dots_matter_outside_gmail(self) -> None:
        """Точки игнорирует только Gmail — у остальных это разные ящики."""
        assert canonical_email('u.ser@yandex.ru') != canonical_email('user@yandex.ru')

    def test_unknown_domain_is_left_alone(self) -> None:
        """Незнакомый домен трогать нельзя: «+» там может быть частью имени."""
        assert canonical_email('user+tag@corp.example') == 'user+tag@corp.example'
        assert canonical_email('u.ser@corp.example') == 'u.ser@corp.example'

    @pytest.mark.parametrize('raw', ['', None, 'not-an-email', 'two@at@signs.com'])
    def test_malformed_input_survives(self, raw: str | None) -> None:
        """Мусор на входе отвергает валидация выше — здесь он не должен падать."""
        assert canonical_email(raw) == (raw or '').strip().lower()

    def test_local_part_cannot_become_empty(self) -> None:
        """«+tag@gmail.com» свернулось бы в «@gmail.com» — общий ящик для всех."""
        assert canonical_email('+tag@gmail.com') == '+tag@gmail.com'
