"""media_file_id тикета принимает только формат Telegram file_id.

Сервер подписывает сохранённый file_id в media_token тем же HMAC, что и ссылки
на файлы DPI-checker (`dpichecker:{kind}:{id}`). Тикет с media_file_id
«dpichecker:report:1» выдавал обычному пользователю подписанную ссылку на CSV.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.cabinet.schemas.tickets import TicketCreateRequest, TicketMediaItem, TicketMessageCreateRequest


@pytest.mark.parametrize('model', [TicketCreateRequest, TicketMessageCreateRequest])
def test_foreign_signing_subject_is_rejected(model) -> None:
    extra = {'title': 'Помогите'} if model is TicketCreateRequest else {}
    with pytest.raises(ValidationError):
        model(message='x', media_type='document', media_file_id='dpichecker:report:1', **extra)


def test_media_items_are_validated_too() -> None:
    with pytest.raises(ValidationError):
        TicketMessageCreateRequest(
            message='x', media_items=[TicketMediaItem(type='document', file_id='dpichecker:noisy:7')]
        )


def test_real_telegram_file_id_is_accepted() -> None:
    file_id = 'BQACAgIAAxkBAAIBY2Zx_Kq9-AbCdEfGhIjKlMnOpQrStUv'
    request = TicketMessageCreateRequest(message='x', media_type='document', media_file_id=file_id)
    assert request.media_file_id == file_id
