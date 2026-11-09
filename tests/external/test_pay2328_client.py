import base64
import hashlib
import hmac
import json

import pytest

from app.config import settings
from app.external.pay2328 import Pay2328Service


KEY = 'test-key'


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> Pay2328Service:
    monkeypatch.setattr(settings, 'PAY2328_MERCHANT_ID', 'project-uuid')
    monkeypatch.setattr(settings, 'PAY2328_API_KEY', KEY)
    return Pay2328Service()


def _documented_sign(data: dict) -> str:
    """Алгоритм из документации 2328.io, записанный независимо от клиента."""
    body = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    encoded = base64.b64encode(body.encode('utf-8')).decode()
    return hmac.new(KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()


WEBHOOK = {
    'uuid': 'db17d490',
    'order_id': 'pay2328_1',
    'amount': '180.00000000',
    'currency': 'RUB',
    'url': 'https://go.2328.io/db17d490',
    'payment_status': 'paid',
    'txid': None,
    'description_ru': 'Пополнение',
    'confirmations': {'current': 20, 'required': 20},
}


def test_request_signature_matches_documented_algorithm(service: Pay2328Service) -> None:
    body = service._serialize(WEBHOOK)
    assert service._sign(body) == _documented_sign(WEBHOOK)


def test_slashes_are_not_escaped(service: Pay2328Service) -> None:
    assert '\\/' not in service._serialize(WEBHOOK)


def test_webhook_with_valid_signature_is_accepted(service: Pay2328Service) -> None:
    assert service.verify_webhook_signature({**WEBHOOK, 'sign': _documented_sign(WEBHOOK)})


@pytest.mark.parametrize('sign', ['', '0' * 64])
def test_webhook_with_bad_signature_is_rejected(service: Pay2328Service, sign: str) -> None:
    assert not service.verify_webhook_signature({**WEBHOOK, 'sign': sign})


def test_webhook_with_changed_amount_is_rejected(service: Pay2328Service) -> None:
    tampered = {**WEBHOOK, 'amount': '1800.00000000', 'sign': _documented_sign(WEBHOOK)}
    assert not service.verify_webhook_signature(tampered)


def test_unconfigured_service_rejects_webhooks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'PAY2328_MERCHANT_ID', None)
    monkeypatch.setattr(settings, 'PAY2328_API_KEY', None)
    assert not Pay2328Service().verify_webhook_signature({'sign': 'x'})
