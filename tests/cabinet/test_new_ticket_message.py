"""Сообщение тикета из запроса кабинета — общее для создания, ответа пользователя и ответа админа."""

import pytest

from app.cabinet.routes.tickets import new_ticket_message
from app.cabinet.schemas.tickets import TicketCreateRequest, TicketMediaItem, TicketMessageCreateRequest


PHOTO_ID = 'AgACAgIAAxkBAAIBQ2Zf' + 'x' * 30
VIDEO_ID = 'BAACAgIAAxkBAAIBRGZf' + 'y' * 30


def test_text_only_has_no_media():
    message = new_ticket_message(5, 9, TicketMessageCreateRequest(message='Привет'), is_from_admin=False)
    assert (message.ticket_id, message.user_id, message.message_text, message.is_from_admin) == (5, 9, 'Привет', False)
    assert message.has_media is False
    assert (message.media_type, message.media_file_id, message.media_caption, message.media_items) == (
        None,
        None,
        None,
        None,
    )
    assert message.created_at is not None


def test_legacy_single_media_fields():
    request = TicketMessageCreateRequest(message='', media_type='photo', media_file_id=PHOTO_ID, media_caption='чек')
    message = new_ticket_message(5, 1, request, is_from_admin=True)
    assert message.is_from_admin is True
    assert (message.has_media, message.media_type, message.media_file_id, message.media_caption) == (
        True,
        'photo',
        PHOTO_ID,
        'чек',
    )
    assert message.media_items is None


@pytest.mark.parametrize('request_cls', [TicketCreateRequest, TicketMessageCreateRequest])
def test_media_items_win_and_first_becomes_primary(request_cls):
    extra = {'title': 'Тема'} if request_cls is TicketCreateRequest else {}
    request = request_cls(
        message='m',
        media_items=[
            TicketMediaItem(type='video', file_id=VIDEO_ID, caption='первое'),
            TicketMediaItem(type='photo', file_id=PHOTO_ID),
        ],
        **extra,
    )
    message = new_ticket_message(5, 9, request, is_from_admin=False)
    assert (message.media_type, message.media_file_id, message.media_caption) == ('video', VIDEO_ID, 'первое')
    assert [item['file_id'] for item in message.media_items] == [VIDEO_ID, PHOTO_ID]
