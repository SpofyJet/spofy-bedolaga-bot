"""xRocket Pay API: запрос счёта, разбор ответа, курс, подпись и вебхук."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.external.xrocket import XRocketService


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def json(self, content_type=None):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _fake_session(monkeypatch, status, body, calls):
    class Session:
        def request(self, method, url, **kw):
            calls.append((method, url, kw))
            return _Resp(status, body)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr('app.external.xrocket.aiohttp.ClientSession', lambda *a, **k: Session())


def _service(monkeypatch):
    monkeypatch.setattr('app.external.xrocket.settings.XROCKET_API_TOKEN', 'tok', raising=False)
    monkeypatch.setattr('app.external.xrocket.settings.XROCKET_BASE_URL', 'https://pay.xrocket.tg', raising=False)
    return XRocketService()


INVOICE = {
    'id': 'inv_1',
    'priceAmount': '2.15',
    'priceCurrency': 'USDT',
    'status': 'active',
    'createdAt': '2026-11-11T10:00:00Z',
    'callback': {'payload': {'payload': 'xrocket_topup_1_17900'}},
    'links': {'telegramBotLink': 'https://t.me/xRocket?start=inv_1'},
}


@pytest.mark.asyncio
async def test_create_invoice_uses_pay_api(monkeypatch):
    calls = []
    _fake_session(monkeypatch, 201, INVOICE, calls)
    svc = _service(monkeypatch)

    res = await svc.create_invoice(2.15, 'USDT', 'Пополнение', 'xrocket_topup_1_17900', expires_in=86400)

    method, url, kw = calls[0]
    assert (method, url) == ('POST', 'https://pay.api.xrocket.exchange/api/v1/invoices')  # старый хост из .env заменён
    assert kw['headers']['Authorization'] == 'Bearer tok'
    assert kw['json']['priceAmount'] == '2.15' and kw['json']['priceCurrency'] == 'USDT'
    assert kw['json']['payCurrencies'] == ['USDT']
    assert kw['json']['expiresIn'] == 86_400_000
    assert res['id'] == 'inv_1' and res['link'] == 'https://t.me/xRocket?start=inv_1'
    assert res['payload'] == 'xrocket_topup_1_17900' and res['status'] == 'active'


@pytest.mark.asyncio
async def test_error_without_envelope_is_failure(monkeypatch):
    _fake_session(monkeypatch, 401, {'type': '/api/problems/unauthorized', 'status': 401}, [])
    assert await _service(monkeypatch).create_invoice(1, 'USDT') is None


@pytest.mark.asyncio
async def test_get_invoice_by_query_and_404_is_expired(monkeypatch):
    calls = []
    _fake_session(monkeypatch, 200, {**INVOICE, 'status': 'paid'}, calls)
    res = await _service(monkeypatch).get_invoice('inv_1')
    assert calls[0][1].endswith('/api/v1/invoice') and calls[0][2]['params'] == {'invoiceId': 'inv_1'}
    assert res['status'] == 'paid'

    _fake_session(monkeypatch, 404, {'type': '/api/problems/invoice_not_found'}, [])
    assert (await _service(monkeypatch).get_invoice('old'))['status'] == 'expired'


@pytest.mark.asyncio
async def test_rate_from_pay_api_without_token(monkeypatch):
    calls = []
    _fake_session(monkeypatch, 200, [{'currency': 'GRAM', 'rate': '100.1'}], calls)
    assert await _service(monkeypatch).get_fiat_rate('GRAM', 'RUB') == 100.1
    assert calls[0][2]['params'] == {'base': 'RUB', 'assets': 'GRAM'}
    assert 'Authorization' not in calls[0][2]['headers']


def _sign(secret, ts, body):
    return hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()


def test_signature(monkeypatch):
    monkeypatch.setattr('app.external.xrocket.settings.XROCKET_WEBHOOK_SECRET', 'whsec', raising=False)
    svc = _service(monkeypatch)
    body = b'{"id":"1","type":"invoice"}'
    ts = str(int(time.time() * 1000))
    assert svc.verify_webhook_signature(body, _sign('whsec', ts, body), ts)
    assert not svc.verify_webhook_signature(body, _sign('other', ts, body), ts)
    old = str(int(time.time() * 1000) - 10 * 60 * 1000)
    assert not svc.verify_webhook_signature(body, _sign('whsec', old, body), old)

    monkeypatch.setattr('app.external.xrocket.settings.XROCKET_WEBHOOK_SECRET', None, raising=False)
    assert not svc.verify_webhook_signature(body, _sign('whsec', ts, body), ts)


def test_webhook_events_map_to_legacy():
    paid = XRocketService.to_legacy_webhook(
        {'id': '9', 'type': 'invoice', 'data': {'event': 'invoice_status_changed', 'invoice': {**INVOICE, 'status': 'paid'}}}
    )
    assert paid['type'] == 'invoicePay'
    assert paid['data']['id'] == 'inv_1' and paid['data']['status'] == 'paid'

    pay = XRocketService.to_legacy_webhook(
        {
            'id': '10',
            'type': 'invoice',
            'data': {
                'event': 'payment_status_changed',
                'invoice': {'id': 'inv_1', 'status': 'active'},
                'payment': {'status': 'paid', 'finalizedAt': '2026-11-11T10:01:00Z'},
            },
        }
    )
    assert pay['data']['status'] == 'paid' and pay['data']['paid'] == '2026-11-11T10:01:00Z'

    cancelled = XRocketService.to_legacy_webhook(
        {'id': '11', 'type': 'invoice', 'data': {'event': 'invoice_status_changed', 'invoice': {**INVOICE, 'status': 'cancelled'}}}
    )
    assert cancelled['data']['status'] == 'cancelled'
    assert json.dumps(cancelled)
