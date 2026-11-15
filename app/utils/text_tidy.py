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


# Знак обходов: в текстах локали и на кнопках это щит Spofy (премиум-эмодзи), а в названии тарифа из базы
# («🏴‍☠️ С Обходами») стоит обычный флаг — на одном экране выходило два разных значка у одного тарифа.
BYPASS_SIGN_EMOJI_ID = '5470133780557631227'
_BYPASS_FLAG = '\U0001f3f4\u200d\u2620'
# Уже обёрнутый знак, содержимое <code>/<pre> (там вложенная разметка запрещена) и сами теги пропускаем целиком.
_BYPASS_SIGN_RE = re.compile(
    r'(<tg-emoji\b[^>]*>.*?</tg-emoji>|<code\b[^>]*>.*?</code>|<pre\b[^>]*>.*?</pre>|<[^<>]*>)'
    '|' + _BYPASS_FLAG + '\ufe0f?',
    re.DOTALL,
)


def brand_bypass_sign(text: str | None) -> str | None:
    """«Голый» 🏴‍☠️ в HTML-тексте → тот же щит Spofy, что в локали и на кнопках. Только для parse_mode=HTML."""
    if not text or _BYPASS_FLAG not in text:
        return text

    def wrap(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            return match.group(0)
        return f"<tg-emoji emoji-id='{BYPASS_SIGN_EMOJI_ID}'>{match.group(0)}</tg-emoji>"

    return _BYPASS_SIGN_RE.sub(wrap, text)
