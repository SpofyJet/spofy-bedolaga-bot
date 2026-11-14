DISPLAY_MODE_BOT = 'bot'
DISPLAY_MODE_WEB = 'web'
DISPLAY_MODE_BOTH = 'both'

VALID_DISPLAY_MODES = (DISPLAY_MODE_BOT, DISPLAY_MODE_WEB, DISPLAY_MODE_BOTH)


def normalize_display_mode(value: str | None) -> str:
    normalized = (value or '').strip().lower()
    if normalized in VALID_DISPLAY_MODES:
        return normalized
    return DISPLAY_MODE_BOTH


def is_visible_in_bot(value: str | None) -> bool:
    return normalize_display_mode(value) in (DISPLAY_MODE_BOT, DISPLAY_MODE_BOTH)


def is_visible_in_web(value: str | None) -> bool:
    return normalize_display_mode(value) in (DISPLAY_MODE_WEB, DISPLAY_MODE_BOTH)
