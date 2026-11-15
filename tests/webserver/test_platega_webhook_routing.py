import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.config import settings
from app.webserver import payments as payments_module
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


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'CRYPTOBOT_ENABLED', False, raising=False)
    monkeypatch.setattr(settings, 'CRYPTOBOT_API_TOKEN', None, raising=False)
    monkeypatch.setattr(settings, 'CRYPTOBOT_WEBHOOK_PATH', '/cryptobot', raising=False)
    monkeypatch.setattr(settings, 'WEBHOOK_URL', 'http://test', raising=False)

    monkeypatch.setattr(settings, 'PLATEGA_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_MERCHANT_ID', 'm', raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_SECRET', 's', raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_WEBHOOK_PATH', '/platega-webhook', raising=False)


def _install_recorder(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch _process_payment_service_callback with a recorder of called method names."""
    recorded: list[str] = []

    async def rec(ps, payload, method_name):
        recorded.append(method_name)
        return True

    monkeypatch.setattr(payments_module, '_process_payment_service_callback', rec)
    return recorded


@pytest.mark.anyio
async def test_platega_one_off_payload_routes_to_legacy_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _install_recorder(monkeypatch)

    router = create_payment_router(DummyBot(), SimpleNamespace())
    assert router is not None

    route = _get_route(router, settings.PLATEGA_WEBHOOK_PATH)
    body = json.dumps({'id': 'tx', 'status': 'CONFIRMED'}).encode('utf-8')
    request = _build_request(
        settings.PLATEGA_WEBHOOK_PATH,
        body=body,
        headers={'X-MerchantId': 'm', 'X-Secret': 's', 'Content-Type': 'application/json'},
    )

    response = await route.endpoint(request)

    assert response.status_code == 200
    assert recorded == ['process_platega_webhook']


@pytest.mark.anyio
async def test_platega_wrong_secret_rejected_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _install_recorder(monkeypatch)

    router = create_payment_router(DummyBot(), SimpleNamespace())
    assert router is not None

    route = _get_route(router, settings.PLATEGA_WEBHOOK_PATH)
    body = json.dumps({'PaymentMethod': 6, 'SubscriptionId': 'ps-1', 'Status': 'CONFIRMED'}).encode('utf-8')
    request = _build_request(
        settings.PLATEGA_WEBHOOK_PATH,
        body=body,
        headers={'X-MerchantId': 'm', 'X-Secret': 'wrong', 'Content-Type': 'application/json'},
    )

    response = await route.endpoint(request)

    assert response.status_code == 401
    assert recorded == []


@pytest.mark.anyio
async def test_platega_camel_case_one_off_still_uses_legacy_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _install_recorder(monkeypatch)

    router = create_payment_router(DummyBot(), SimpleNamespace())
    assert router is not None

    route = _get_route(router, settings.PLATEGA_WEBHOOK_PATH)
    body = json.dumps({'id': 'tx', 'status': 'CONFIRMED', 'paymentMethod': 2}).encode('utf-8')
    request = _build_request(
        settings.PLATEGA_WEBHOOK_PATH,
        body=body,
        headers={'X-MerchantId': 'm', 'X-Secret': 's', 'Content-Type': 'application/json'},
    )

    response = await route.endpoint(request)

    assert recorded == ['process_platega_webhook']
    assert response.status_code == 200
