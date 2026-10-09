"""Причёска текста сообщений: лишние пустые строки и пробелы по краям.

Шаблоны собираются из кусков, и пустая подстановка («{discount}», «{warning}», список без устройств) оставляла
в сообщении две-три пустых строки подряд: экран выглядел дырявым. Правило одно: не больше одной пустой строки
подряд, никаких пробелов в конце строк и пустых строк по краям.
"""

from __future__ import annotations

import re


_BLANK_RUN = re.compile(r'\n[ \t ]*(?:\n[ \t ]*){2,}')
_TRAILING_SPACES = re.compile(r'[ \t ]+\n')


def tidy_text(text: str | None) -> str | None:
    """Схлопывает 2+ пустые строки в одну и убирает хвостовые пробелы. ``None`` и пустое возвращает как есть."""
    if not text:
        return text
    cleaned = _TRAILING_SPACES.sub('\n', text)
    cleaned = _BLANK_RUN.sub('\n\n', cleaned)
    return cleaned.strip('\n') or text
