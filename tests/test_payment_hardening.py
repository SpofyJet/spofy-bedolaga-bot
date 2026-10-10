"""Секреты не попадают в лог; CryptoBot не-JSON; короткий кэш статуса WATA."""

from unittest.mock import AsyncMock

from app.logging_config import _redact_event_dict, redact_secrets
from app.services.wata_service import WataService


def test_header_dump_of_an_exception_is_masked():
    text = "ContentTypeError(headers=<CIMultiDictProxy('Host': 'pay.crypt.bot', 'Crypto-Pay-API-Token': '605182:AAoc0dqrHLTqfkGx5I0TG9EOI2Q8yxekeNR'>)"
    cleaned = redact_secrets(text)
    assert 'AAoc0dqrHLTqf' not in cleaned
    assert "'Crypto-Pay-API-Token': '***'" in cleaned
    assert 'pay.crypt.bot' in cleaned


def test_platega_and_bearer_headers_and_bot_tokens_are_masked():
    cleaned = redact_secrets(
        "{'X-Secret': 'abc123', 'Authorization': 'Bearer xyz'} bot 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    )
    assert 'abc123' not in cleaned and 'xyz' not in cleaned and 'ABCdef' not in cleaned


def test_plain_text_is_left_alone():
    assert redact_secrets('Создан платёж на 270 ₽, user_id=18046') == 'Создан платёж на 270 ₽, user_id=18046'


def test_event_dict_masks_strings_and_exceptions_but_keeps_exc_info():
    exc = RuntimeError("{'X-Secret': 'topsecret'}")
    out = _redact_event_dict(None, 'error', {'event': 'x', 'error': exc, 'exc_info': (RuntimeError, exc, None), 'n': 5})
    assert 'topsecret' not in out['error']
    assert out['exc_info'][1] is exc
    assert out['n'] == 5


async def test_wata_status_is_cached_briefly_unless_final(monkeypatch):
    WataService._status_cache.clear()
    service = WataService.__new__(WataService)
    request = AsyncMock(return_value={'status': 'Opened'})
    monkeypatch.setattr(service, '_request', request, raising=False)
    await service.get_payment_link('L1')
    await service.get_payment_link('L1')
    assert request.await_count == 1  # второй вызов — из кэша

    request.return_value = {'status': 'Closed'}
    await service.get_payment_link('L2')
    await service.get_payment_link('L2')
    assert request.await_count == 3  # оконченный статус не кэшируем: он должен быть свежим


async def test_wata_cache_expires(monkeypatch):
    WataService._status_cache.clear()
    service = WataService.__new__(WataService)
    request = AsyncMock(return_value={'status': 'Opened'})
    monkeypatch.setattr(service, '_request', request, raising=False)
    await service.get_transaction('T1')
    key, (stamp, data) = next(iter(WataService._status_cache.items()))
    WataService._status_cache[key] = (stamp - 60, data)
    await service.get_transaction('T1')
    assert request.await_count == 2
