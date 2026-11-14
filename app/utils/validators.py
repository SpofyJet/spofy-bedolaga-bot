import html as html_module
import re


ALLOWED_HTML_TAGS = {
    'b',
    'strong',  # жирный
    'i',
    'em',  # курсив
    'u',
    'ins',  # подчёркнутый
    's',
    'strike',
    'del',  # зачёркнутый
    'code',  # моноширинный
    'pre',  # блок кода
    'a',  # ссылка
    'blockquote',  # цитата
    'tg-spoiler',  # спойлер
    'tg-emoji',  # кастомный эмодзи
    'span',  # для class="tg-spoiler"
}

SELF_CLOSING_TAGS = {'br', 'hr', 'img'}

# Разрешённые атрибуты для HTML-тегов
ALLOWED_TAG_ATTRIBUTES = {
    'a': {'href'},
    'tg-emoji': {'emoji-id'},
    'span': {'class'},
}

# Разрешённые URI-схемы в href (allowlist вместо blocklist)
SAFE_URI_SCHEMES = re.compile(r'^(https?://|tg://|mailto:|tel:)', re.IGNORECASE)


def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def sanitize_html(text: str) -> str:
    """
    Безопасно санитизирует HTML-текст, заменяя HTML-сущности на соответствующие теги,
    при этом предотвращая XSS-уязвимости за счет безопасной обработки атрибутов.

    Args:
        text (str): Текст с HTML-сущностями (например, &lt;b&gt; жирный &lt;/b&gt;)

    Returns:
        str: Санитизированный HTML-текст (например, <b> жирный </b>)
    """
    if not text:
        return text

    # Для безопасности нужно обработать разрешенные теги, заменяя их сущности на теги
    # Но при этом безопасно обрабатывая атрибуты, чтобы избежать XSS

    allowed_tags = ALLOWED_HTML_TAGS.union(SELF_CLOSING_TAGS)

    # Обработка всех разрешенных тегов
    for tag in allowed_tags:
        # Паттерн: захватываем &lt;tag&gt;, &lt;/tag&gt;, или &lt;tag атрибуты&gt;
        # [^>]*? - ленивый захват до >
        pattern = rf'(&lt;)(/?{tag}\b)([^>]*?)(&gt;)'

        tag_lower = tag.lower()

        def replace_tag(match, _tag=tag_lower):
            full_tag_content = match.group(2)  # /?tagname
            attrs_part = match.group(3).removeprefix(' ')  # атрибуты (без >)

            if not attrs_part:
                return f'<{full_tag_content}>'

            # Полное декодирование HTML-сущностей для корректной проверки атрибутов
            processed_attrs = html_module.unescape(attrs_part)

            # Проверяем whitelist атрибутов для данного тега
            allowed_attrs = ALLOWED_TAG_ATTRIBUTES.get(_tag)
            if allowed_attrs is None:
                # Тег без whitelist — удаляем ВСЕ атрибуты
                return f'<{full_tag_content}>'

            filtered_parts = []
            for attr_match in re.finditer(r'([a-zA-Z][\w-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', processed_attrs):
                attr_name = attr_match.group(1).lower()
                attr_value = attr_match.group(2) if attr_match.group(2) is not None else attr_match.group(3)
                if attr_name not in allowed_attrs:
                    continue
                # href: allowlist безопасных URI-схем
                if attr_name == 'href':
                    # Нормализуем: убираем control chars и пробелы из начала значения
                    normalized = re.sub(r'[\x00-\x1f\x7f\s]+', '', attr_value)
                    if not SAFE_URI_SCHEMES.match(normalized):
                        continue
                filtered_parts.append(f'{attr_name}="{attr_value}"')
            processed_attrs = ' '.join(filtered_parts)

            if processed_attrs:
                return f'<{full_tag_content} {processed_attrs}>'
            return f'<{full_tag_content}>'

        text = re.sub(pattern, replace_tag, text, flags=re.IGNORECASE)

    return text


def sanitize_telegram_name(name: str | None) -> str | None:
    """Санитизация Telegram-имени для безопасной вставки в HTML и хранения.
    Заменяет угловые скобки и амперсанд на безопасные визуальные аналоги.
    """
    if not name:
        return name
    try:
        return name.replace('<', '‹').replace('>', '›').replace('&', '＆').strip()
    except Exception:
        return name


def validate_html_tags(text: str) -> tuple[bool, str]:
    if not text:
        return True, ''

    # [^<>], а не [^>]: на тексте из множества «<a» без закрывающей скобки
    # второй вариант перебирает хвост заново с каждого «<». Замер на 80 КБ —
    # 0.84 с здесь и 10 с в проверке структуры ниже, а длина HTML правовых
    # страниц из кабинета ничем не ограничена. Possessive-квантификаторы
    # также исключают перебор границы между длинным именем тега и атрибутами.
    tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9-]*+)[^<>]*+>'
    tags = re.findall(tag_pattern, text)

    for is_closing, tag_name in tags:
        tag_name_lower = tag_name.lower()

        if tag_name_lower not in ALLOWED_HTML_TAGS and tag_name_lower not in SELF_CLOSING_TAGS:
            return False, f'Неподдерживаемый тег: <{tag_name}>'

    return validate_html_structure(text)


def validate_html_structure(text: str) -> tuple[bool, str]:
    tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9-]*+)[^<>]*+>'

    matches = re.finditer(tag_pattern, text)
    tag_stack = []

    for match in matches:
        full_tag = match.group(0)
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()

        if full_tag.endswith('/>') or tag_name in SELF_CLOSING_TAGS:
            continue

        if not is_closing:
            tag_stack.append(tag_name)
        else:
            if not tag_stack:
                return False, f'Закрывающий тег без открывающего: </{tag_name}>'

            last_tag = tag_stack.pop()
            if last_tag != tag_name:
                return False, f'Неправильная вложенность тегов: ожидался </{last_tag}>, найден </{tag_name}>'

    if tag_stack:
        return False, f'Незакрытый тег: <{tag_stack[-1]}>'

    return True, ''


def get_html_help_text() -> str:
    return """<b>Поддерживаемые HTML теги:</b>

• <code>&lt;b&gt;жирный&lt;/b&gt;</code> или <code>&lt;strong&gt;&lt;/strong&gt;</code>
• <code>&lt;i&gt;курсив&lt;/i&gt;</code> или <code>&lt;em&gt;&lt;/em&gt;</code>
• <code>&lt;u&gt;подчёркнутый&lt;/u&gt;</code>
• <code>&lt;s&gt;зачёркнутый&lt;/s&gt;</code>
• <code>&lt;code&gt;моноширинный&lt;/code&gt;</code>
• <code>&lt;pre&gt;блок кода&lt;/pre&gt;</code>
• <code>&lt;a href="url"&gt;ссылка&lt;/a&gt;</code>
• <code>&lt;blockquote&gt;цитата&lt;/blockquote&gt;</code>
• <code>&lt;tg-spoiler&gt;спойлер&lt;/tg-spoiler&gt;</code>
• <code>&lt;tg-emoji emoji-id="123"&gt;😀&lt;/tg-emoji&gt;</code>

<b>⚠️ Важные правила:</b>
• Каждый открывающий тег должен быть закрыт
• Теги должны быть правильно вложены
• Атрибуты ссылок берите в кавычки

<b>❌ Неправильно:</b>
<code>&lt;b&gt;жирный &lt;i&gt;курсив&lt;/b&gt;&lt;/i&gt;</code>

<b>✅ Правильно:</b>
<code>&lt;b&gt;жирный &lt;i&gt;курсив&lt;/i&gt;&lt;/b&gt;</code>"""
