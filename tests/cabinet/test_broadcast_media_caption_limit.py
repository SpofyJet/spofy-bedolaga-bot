"""Лимит подписи к медиа в рассылке считается по видимому тексту, а не по HTML."""

import pytest
from fastapi import HTTPException

from app.cabinet.routes.admin_broadcasts import _ensure_media_caption_fits


def test_markup_does_not_count_towards_caption_limit():
    visible = 'а' * 1000
    caption = f'<b>{visible}</b>' + '<tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>' * 5
    assert len(caption) > 1024
    _ensure_media_caption_fits(caption)  # 1005 видимых символов — Telegram примет


def test_visible_text_over_limit_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _ensure_media_caption_fits('<i>' + 'б' * 1025 + '</i>')
    assert exc.value.status_code == 400
