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


_TG_EMOJI_RE = re.compile(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', re.DOTALL)
_HTML_TAG_RE = re.compile(r'</?[a-zA-Z][a-zA-Z0-9-]*(?:\s[^<>]*)?/?>')
# Предел Telegram для текста answerCallbackQuery: длиннее — запрос падает целиком.
ALERT_TEXT_LIMIT = 200


def strip_tg_emoji(text: str) -> str:
    """<tg-emoji …>🎁</tg-emoji> → 🎁 for text that leaves the bot as plain text (copied, forwarded, shared)."""
    return _TG_EMOJI_RE.sub(r'\1', text)


def plain_alert_text(text: str) -> str:
    """Текст для всплывающего окна после нажатия кнопки: HTML там не разбирается.

    <tg-emoji …>✅</tg-emoji> → ✅, прочие теги (<b>, <i>, <code>…) снимаются, сущности
    (&amp;, &lt;) раскрываются; слишком длинный текст обрезается по пределу Telegram.
    """
    import html

    if '<' not in text and '&' not in text and len(text) <= ALERT_TEXT_LIMIT:
        return text
    plain = _TG_EMOJI_RE.sub(r'\1', text)
    plain = _HTML_TAG_RE.sub('', plain)
    plain = html.unescape(plain)
    if len(plain) > ALERT_TEXT_LIMIT:
        plain = plain[: ALERT_TEXT_LIMIT - 1].rstrip() + '…'
    return plain
