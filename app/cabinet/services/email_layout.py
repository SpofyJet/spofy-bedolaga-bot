"""
Общая обёртка писем (layout): один редактируемый HTML-каркас для всех писем.

Тексты писем редактировались, а обёртка — шапка с названием сервиса, цвета,
подвал — была зашита в код; поменять её можно было только вставив полный HTML
в каждый из 50 типов на каждом из 5 языков. Теперь обёртка хранится как
псевдо-тип ``email_layout`` в той же таблице email_templates и редактируется в
том же редакторе. Плейсхолдер ``{content}`` обязателен — в него встаёт тело
письма; без сохранённой обёртки работает встроенная DEFAULT_EMAIL_LAYOUT.

Рендер писем синхронный, а хранилище асинхронное, поэтому обёртка живёт в
кэше процесса: его обновляет каждый чокпойнт отправки (get_rendered_override)
не чаще раза в LAYOUT_CACHE_TTL_SECONDS и сразу — сохранение в редакторе.
Ошибка базы — это «обёртки нет», а не потерянное письмо.
"""

import html
import re
import time
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import AsyncSessionLocal


logger = structlog.get_logger(__name__)

EMAIL_LAYOUT_TYPE = 'email_layout'
CONTENT_PLACEHOLDER = '{content}'
LAYOUT_CACHE_TTL_SECONDS = 60

# Плейсхолдеры обёртки в порядке подстановки: content первым, чтобы переменные
# внутри вставленного письма ({cabinet_url} и т.п.) тоже подставились.
LAYOUT_CONTEXT_VARS = [
    'content',
    'service_name',
    'footer_text',
    'unsubscribe_block',
    'unsubscribe_url',
    'cabinet_url',
    'support_username',
    # Данные получателя: рендер письма передаёт их в обёртку вместе с телом.
    'username',
    'email',
    'date',
    # Скрытая первая строка письма — её почтовики показывают в списке рядом с темой.
    'preheader',
]
# HTML-значения — не экранируем.
_RAW_VARS = frozenset({'content', 'unsubscribe_block'})

# Маркеры вокруг тела письма: по ним редактор достаёт фрагмент из готового
# письма независимо от того, как выглядит обёртка.
CONTENT_START = '<!-- email-content-start -->'
CONTENT_END = '<!-- email-content-end -->'

FOOTER_TEXTS = {
    'ru': 'Это автоматическое сообщение. Пожалуйста, не отвечайте на это письмо.',
    'en': 'This is an automated message. Please do not reply to this email.',
}

UNSUBSCRIBE_TEXTS = {
    'ru': 'Отписаться от рассылок',
    'en': 'Unsubscribe from marketing emails',
}

# Встроенная обёртка: таблицы и стили, которые переживают Gmail, Mail.ru,
# Яндекс и Outlook. Классы тела письма (.highlight, .button, .details…) описаны
# в <style> для браузеров и превью редактора, а перед отправкой
# inline_email_styles() дублирует их в style="" — почтовики, режущие <style>,
# показывают письмо так же. Атрибут data-sp-email помечает документы этой
# обёртки: чужие сохранённые обёртки инлайнер не трогает.
DEFAULT_EMAIL_LAYOUT = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="x-apple-disable-message-reformatting">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>{service_name}</title>
    <style>
        body { margin: 0; padding: 0; background-color: #eef2f7; -webkit-text-size-adjust: 100%; }
        .sp-card { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.6; color: #334155; }
        .sp-card h1, .sp-card h2 { margin: 0 0 12px; font-size: 22px; line-height: 1.3; font-weight: 700; color: #0f172a; }
        .sp-card h3 { margin: 18px 0 8px; font-size: 16px; font-weight: 700; color: #0f172a; }
        .sp-card p { margin: 0 0 12px; }
        .sp-card a { color: #2563eb; }
        .sp-card strong { color: #0f172a; }
        .lead { font-size: 16px; }
        .highlight { background-color: #f1f5f9; border-left: 4px solid #3b82f6; border-radius: 10px; padding: 14px 18px 2px; margin: 18px 0; }
        .highlight.success { border-left-color: #22c55e; }
        .highlight.warning { border-left-color: #f59e0b; }
        .highlight.danger { border-left-color: #ef4444; }
        .details { width: 100%; border-collapse: collapse; margin: 4px 0 18px; }
        .details td { padding: 9px 0; border-bottom: 1px solid #e2e8f0; font-size: 14px; }
        .details .k { color: #64748b; }
        .details .v { text-align: right; font-weight: 600; color: #0f172a; }
        .cta { text-align: center; margin: 26px 0 22px; }
        .button { display: inline-block; background-color: #2563eb; color: #ffffff !important; text-decoration: none; font-weight: 600; font-size: 16px; line-height: 20px; padding: 14px 28px; border-radius: 10px; }
        .button.secondary { background-color: #e2e8f0; color: #0f172a !important; }
        .code { font-family: 'SFMono-Regular', Menlo, Consolas, 'Courier New', monospace; font-size: 32px; font-weight: 700; letter-spacing: 8px; text-align: center; color: #0f172a; background-color: #f1f5f9; border-radius: 12px; padding: 18px 12px; margin: 18px 0; }
        .note { font-size: 13px; line-height: 1.5; color: #64748b; }
        .link { font-size: 13px; word-break: break-all; }
        .amount { font-size: 22px; font-weight: 700; color: #16a34a; }
        .amount.negative { color: #dc2626; }
        @media (max-width: 600px) {
            .sp-card { padding: 26px 20px 14px !important; }
            .sp-header { padding: 18px 20px !important; }
            .button { display: block !important; }
        }
        @media (prefers-color-scheme: dark) {
            body, .sp-bg { background-color: #0a0f1a !important; }
            .sp-card { background-color: #0f172a !important; color: #cbd5e1 !important; }
            .sp-card h1, .sp-card h2, .sp-card h3, .sp-card strong, .details .v, .code { color: #f1f5f9 !important; }
            .highlight, .code { background-color: #1e293b !important; }
            .details td { border-bottom-color: #1e293b !important; }
            .details .k, .note, .footer { color: #94a3b8 !important; }
            .button.secondary { background-color: #1e293b !important; color: #f1f5f9 !important; }
        }
    </style>
</head>
<body data-sp-email="1" style="margin: 0; padding: 0; background-color: #eef2f7;">
    <div class="preheader" style="display: none; max-height: 0; overflow: hidden; opacity: 0; mso-hide: all; font-size: 1px; line-height: 1px; color: #eef2f7;">{preheader}&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;</div>
    <table role="presentation" class="sp-bg" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#eef2f7" style="background-color: #eef2f7;">
        <tr>
            <td align="center" style="padding: 24px 12px;">
                <table role="presentation" class="container" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 560px; width: 100%;">
                    <tr>
                        <td class="sp-header" bgcolor="#0f172a" style="background-color: #0f172a; border-radius: 16px 16px 0 0; padding: 20px 28px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 700; color: #ffffff;">
                            <span style="color: #3b82f6;">&#9679;</span>&nbsp;{service_name}
                        </td>
                    </tr>
                    <tr>
                        <td class="sp-card content" bgcolor="#ffffff" style="background-color: #ffffff; border-radius: 0 0 16px 16px; padding: 32px 28px 18px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.6; color: #334155;">
                            {content}
                        </td>
                    </tr>
                    <tr>
                        <td class="footer" align="center" style="padding: 18px 28px 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 12px; line-height: 1.5; color: #64748b;">
                            <p style="margin: 0 0 6px;">{footer_text}</p>
                            {unsubscribe_block}
                            <p style="margin: 6px 0 0;">&copy; {service_name}</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


# ============ Инлайн-стили перед отправкой ============

LAYOUT_MARKER = 'data-sp-email="1"'
_INLINED_MARKER = 'data-sp-email="inlined"'

# Те же правила, что в <style> встроенной обёртки, — для почтовиков, которые
# <style> вырезают. Порядок: стиль тега, потом классы, потом то, что уже
# написано в style="" (оно побеждает как последнее).
_TAG_STYLES = {
    'h1': 'margin:0 0 12px;font-size:22px;line-height:1.3;font-weight:700;color:#0f172a;',
    'h2': 'margin:0 0 12px;font-size:22px;line-height:1.3;font-weight:700;color:#0f172a;',
    'h3': 'margin:18px 0 8px;font-size:16px;font-weight:700;color:#0f172a;',
    'p': 'margin:0 0 12px;',
    'a': 'color:#2563eb;',
    'strong': 'color:#0f172a;',
}
_CLASS_STYLES = {
    'lead': 'font-size:16px;',
    'highlight': (
        'background-color:#f1f5f9;border-left:4px solid #3b82f6;border-radius:10px;padding:14px 18px 2px;margin:18px 0;'
    ),
    'details': 'width:100%;border-collapse:collapse;margin:4px 0 18px;',
    'k': 'padding:9px 12px 9px 0;border-bottom:1px solid #e2e8f0;font-size:14px;color:#64748b;',
    'v': 'padding:9px 0;border-bottom:1px solid #e2e8f0;font-size:14px;text-align:right;font-weight:600;color:#0f172a;',
    'cta': 'text-align:center;margin:26px 0 22px;',
    'button': (
        'display:inline-block;background-color:#2563eb;color:#ffffff;text-decoration:none;font-weight:600;'
        'font-size:16px;line-height:20px;padding:14px 28px;border-radius:10px;'
    ),
    'code': (
        "font-family:'SFMono-Regular',Menlo,Consolas,'Courier New',monospace;font-size:32px;font-weight:700;"
        'letter-spacing:8px;text-align:center;color:#0f172a;background-color:#f1f5f9;border-radius:12px;'
        'padding:18px 12px;margin:18px 0;'
    ),
    'note': 'font-size:13px;line-height:1.5;color:#64748b;',
    'link': 'font-size:13px;word-break:break-all;',
    'amount': 'font-size:22px;font-weight:700;color:#16a34a;',
}
# Модификаторы действуют только вместе с базовым классом.
_MODIFIER_STYLES = {
    ('highlight', 'success'): 'border-left-color:#22c55e;',
    ('highlight', 'warning'): 'border-left-color:#f59e0b;',
    ('highlight', 'danger'): 'border-left-color:#ef4444;',
    ('button', 'secondary'): 'background-color:#e2e8f0;color:#0f172a;',
    ('amount', 'negative'): 'color:#dc2626;',
}
_TAG_RE = re.compile(r'<(h1|h2|h3|p|a|div|span|td|table|strong)\b([^>]*)>', re.IGNORECASE)
_CLASS_RE = re.compile(r'\sclass="([^"]*)"', re.IGNORECASE)
_STYLE_RE = re.compile(r'\sstyle="([^"]*)"', re.IGNORECASE)


def _inline_tag(match: re.Match) -> str:
    tag, attrs = match.group(1), match.group(2)
    class_match = _CLASS_RE.search(attrs)
    classes = class_match.group(1).split() if class_match else []
    added = _TAG_STYLES.get(tag.lower(), '')
    for name in classes:
        added += _CLASS_STYLES.get(name, '')
    for (base, modifier), style in _MODIFIER_STYLES.items():
        if base in classes and modifier in classes:
            added += style
    if not added:
        return match.group(0)
    style_match = _STYLE_RE.search(attrs)
    if style_match:
        existing = style_match.group(1).strip()
        merged = added + existing
        attrs = attrs[: style_match.start()] + f' style="{merged}"' + attrs[style_match.end() :]
    else:
        self_closing = attrs.endswith('/')
        attrs = (attrs[:-1] if self_closing else attrs) + f' style="{added}"' + ('/' if self_closing else '')
    return f'<{tag}{attrs}>'


def inline_email_styles(document: str) -> str:
    """Дублирует стили классов встроенной обёртки в style="" — только у её писем и один раз.

    Свои сохранённые обёртки и полные HTML-документы из редактора не трогаем:
    у них свои стили, и метки data-sp-email у них нет.
    """
    if not document or LAYOUT_MARKER not in document:
        return document
    head, sep, body = document.partition('<body')
    if not sep:
        return document
    body = _TAG_RE.sub(_inline_tag, body)
    return head + sep + body.replace(LAYOUT_MARKER, _INLINED_MARKER, 1)


def layout_is_valid(layout_html: str) -> bool:
    """Обёртка без {content} проглотила бы тело каждого письма."""
    return CONTENT_PLACEHOLDER in (layout_html or '')


def unsubscribe_block(unsubscribe_url: str, language: str) -> str:
    """Ссылка отписки — только у маркетинговых писем, у остальных пусто."""
    if not unsubscribe_url:
        return ''
    label = UNSUBSCRIBE_TEXTS.get(language, UNSUBSCRIBE_TEXTS['ru'])
    return (
        f'<p style="margin: 0 0 6px;"><a href="{html.escape(unsubscribe_url, quote=True)}" '
        f'style="color: #64748b; text-decoration: underline;">{label}</a></p>'
    )


def build_layout_context(language: str, *, content: str = '', unsubscribe_url: str = '') -> dict[str, str]:
    """Реальные значения плейсхолдеров обёртки для языка.

    Данные получателя здесь пустые — их подмешивает рендер письма; пустая
    строка гарантирует, что литерал {username} не уйдёт в письмо.
    """
    from datetime import UTC, datetime

    from app.utils.timezone import format_email_datetime

    return {
        'content': content,
        'service_name': settings.SMTP_FROM_NAME or 'VPN Service',
        'footer_text': FOOTER_TEXTS.get(language, FOOTER_TEXTS['ru']),
        'unsubscribe_block': unsubscribe_block(unsubscribe_url, language),
        # Голая ссылка — для своего текста отписки вместо готового блока.
        'unsubscribe_url': unsubscribe_url or '',
        'cabinet_url': settings.CABINET_URL or '',
        'support_username': settings.SUPPORT_USERNAME or '',
        'username': '',
        'email': '',
        'date': format_email_datetime(datetime.now(UTC), fmt='%d.%m.%Y'),
        'preheader': '',
    }


def render_email_layout(
    layout_html: str,
    language: str,
    context: dict[str, Any] | None = None,
    *,
    mark_content: bool = True,
) -> str:
    """Подставляет плейсхолдеры обёртки. Недостающие берутся из build_layout_context.

    ``content`` и ``unsubscribe_block`` — HTML, остальное экранируется.
    ``mark_content`` обрамляет тело маркерами для extract_content_fragment;
    редактор обёртки получает дефолт без них.
    """
    given = context or {}
    values = {**build_layout_context(language, unsubscribe_url=str(given.get('unsubscribe_url') or '')), **given}
    result = layout_html
    for key in LAYOUT_CONTEXT_VARS:
        raw = values.get(key)
        value = '' if raw is None else str(raw)
        if key == 'content' and mark_content:
            value = f'{CONTENT_START}{value}{CONTENT_END}'
        elif key not in _RAW_VARS:
            value = html.escape(value)
        result = result.replace(f'{{{key}}}', value)
    return result


def extract_content_fragment(rendered_html: str) -> str | None:
    """Тело письма из готового HTML по маркерам, None если маркеров нет."""
    start = rendered_html.find(CONTENT_START)
    end = rendered_html.find(CONTENT_END)
    if start < 0 or end < 0 or end < start:
        return None
    return rendered_html[start + len(CONTENT_START) : end].strip()


# ============ Кэш сохранённой обёртки ============

_cache: dict[str, str] = {}
_loaded_at: float | None = None


def _monotonic() -> float:
    return time.monotonic()


def reset_email_layout_cache() -> None:
    global _cache, _loaded_at
    _cache = {}
    _loaded_at = None


def set_cached_email_layouts(layouts: dict[str, str]) -> None:
    """Заменяет кэш; обёртки без {content} отбрасываются с предупреждением."""
    global _cache, _loaded_at
    valid = {lang: body for lang, body in layouts.items() if layout_is_valid(body)}
    for lang in set(layouts) - set(valid):
        logger.warning('Сохранённая обёртка писем без {content} пропущена', language=lang)
    _cache = valid
    _loaded_at = _monotonic()


def get_cached_email_layout(language: str) -> str | None:
    """Обёртка для языка; нет своей — русская; нет и её — None (встроенная)."""
    return _cache.get(language) or _cache.get('ru')


def resolve_email_layout(language: str) -> str:
    return get_cached_email_layout(language) or DEFAULT_EMAIL_LAYOUT


def is_layout_cache_stale() -> bool:
    return _loaded_at is None or _monotonic() - _loaded_at > LAYOUT_CACHE_TTL_SECONDS


async def _load_layouts(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(
        text(
            'SELECT language, body_html FROM email_templates WHERE notification_type = :ntype AND is_active = :active'
        ),
        {'ntype': EMAIL_LAYOUT_TYPE, 'active': True},
    )
    return {row[0]: row[1] for row in result.fetchall()}


async def refresh_email_layout_cache(db: AsyncSession | None = None, *, force: bool = False) -> None:
    """Подтягивает сохранённые обёртки, если кэш устарел (или force после сохранения)."""
    global _loaded_at
    if not force and not is_layout_cache_stale():
        return
    try:
        if db is not None:
            layouts = await _load_layouts(db)
        else:
            async with AsyncSessionLocal() as session:
                layouts = await _load_layouts(session)
    except Exception as e:
        # Старый кэш остаётся, но время загрузки обновляем — иначе каждое письмо
        # заново долбило бы недоступную базу.
        logger.warning('Не удалось загрузить обёртку писем — остаётся текущая', error=e)
        _loaded_at = _monotonic()
        return
    set_cached_email_layouts(layouts)
