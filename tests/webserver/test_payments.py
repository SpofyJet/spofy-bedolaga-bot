import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.config import settings
from app.webserver.payments import create_payment_router


class DummyBot:
    pass


def _get_route(router, path: str, method: str = 'POST'):
    for route in router.routes:
        if getattr(route, 'path', '') == path and method in getattr(route, 'methods', set()):
            return route
    raise AssertionError(f'Route {path} with method {method} not found')


def _build_request(
    path: str,
    body: bytes,
    headers: dict[str, str],
    client_ip: str | None = '185.71.76.1',
) -> Request:
    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'method': 'POST',
        'path': path,
        'headers': [(k.lower().encode('latin-1'), v.encode('latin-1')) for k, v in headers.items()],
    }

    if client_ip is not None:
        scope['client'] = (client_ip, 12345)

    async def receive() -> dict:
        return {'type': 'http.request', 'body': body, 'more_body': False}

    return Request(scope, receive)


@pytest.mark.anyio
async def test_cryptobot_missing_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'CRYPTOBOT_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'CRYPTOBOT_API_TOKEN', 'token', raising=False)
    monkeypatch.setattr(settings, 'CRYPTOBOT_WEBHOOK_SECRET', 'secret', raising=False)

    router = create_payment_router(DummyBot(), SimpleNamespace())
    assert router is not None

    route = _get_route(router, settings.CRYPTOBOT_WEBHOOK_PATH)
    request = _build_request(
        settings.CRYPTOBOT_WEBHOOK_PATH,
        body=json.dumps({'test': 'value'}).encode('utf-8'),
        headers={},
    )

    response = await route.endpoint(request)

    assert response.status_code == 401
    payload = json.loads(response.body.decode('utf-8'))
    assert payload['reason'] == 'missing_signature'


@pytest.mark.anyio
async def test_cryptobot_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'CRYPTOBOT_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'CRYPTOBOT_API_TOKEN', 'token', raising=False)
    monkeypatch.setattr(settings, 'CRYPTOBOT_WEBHOOK_SECRET', 'secret', raising=False)

    class StubCryptoBotService:
        @staticmethod
        def verify_webhook_signature(body: str, signature: str) -> bool:
            return False

    monkeypatch.setattr('app.external.cryptobot.CryptoBotService', StubCryptoBotService)

    router = create_payment_router(DummyBot(), SimpleNamespace())
    assert router is not None

    route = _get_route(router, settings.CRYPTOBOT_WEBHOOK_PATH)
    request = _build_request(
        settings.CRYPTOBOT_WEBHOOK_PATH,
        body=json.dumps({'test': 'value'}).encode('utf-8'),
        headers={'Crypto-Pay-API-Signature': 'sig'},
    )

    response = await route.endpoint(request)

    assert response.status_code == 401
